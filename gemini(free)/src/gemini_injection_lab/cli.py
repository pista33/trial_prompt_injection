"""Command-line interface. Network access is opt-in and never used by doctor/dry-run."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import re
import sys
import time
from pathlib import Path
from typing import Any


def _safe_run_view(record: Any) -> dict[str, Any]:
    return {
        "experiment_id": record.experiment_id,
        "run_id": record.run_id,
        "repetition": record.repetition,
        "execution_mode": record.execution_mode,
        "case_id": record.case.id,
        "prompt_profile": record.case.prompt_profile,
        "requested_model": record.model.requested_name,
        "hashes": record.hashes.model_dump(mode="json"),
        "interaction_status": record.interaction.status,
        "api_error": record.api_error.model_dump(mode="json"),
    }


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _installed_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _major_minor(version: str | None) -> tuple[int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)", version or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _doctor(project_root: Path) -> int:
    checks: dict[str, dict[str, Any]] = {}
    version_ok = sys.version_info >= (3, 12)
    checks["python"] = {"ok": version_ok, "version": platform.python_version()}
    sdk_version = _installed_version("google-genai")
    sdk_tuple = _major_minor(sdk_version)
    sdk_ok = bool(sdk_tuple and (2, 3) <= sdk_tuple < (3, 0))
    checks["google_genai"] = {
        "ok": sdk_ok,
        "version": sdk_version,
    }
    pydantic_version = _installed_version("pydantic")
    dotenv_version = _installed_version("python-dotenv")
    pytest_version = _installed_version("pytest")
    checks["pydantic"] = {
        "ok": bool(_major_minor(pydantic_version) and _major_minor(pydantic_version) >= (2, 7)),
        "version": pydantic_version,
    }
    checks["python_dotenv"] = {
        "ok": bool(_major_minor(dotenv_version) and _major_minor(dotenv_version) >= (1, 0)),
        "version": dotenv_version,
    }
    checks["pytest"] = {
        "ok": bool(_major_minor(pytest_version) and _major_minor(pytest_version) >= (8, 0)),
        "version": pytest_version,
    }
    required = [
        project_root / "pyproject.toml",
        project_root / "data" / "cases.json",
        project_root / "prompts" / "system_baseline.txt",
        project_root / "prompts" / "system_hardened.txt",
        project_root / "prompts" / "user_task.txt",
        project_root / "data" / "sandbox" / "documents",
    ]
    checks["project_files"] = {
        "ok": all(path.exists() for path in required),
        "checked": len(required),
    }
    try:
        cases_data = json.loads(required[1].read_text(encoding="utf-8"))
        case_ids = sorted(item["id"] for item in cases_data)
        case_count = len(case_ids)
        cases_ok = case_ids == ["B-01", "B-02", "PI-01", "PI-02", "PI-03", "PI-04"]
    except Exception as error:
        case_count = 0
        cases_ok = False
        checks["case_error"] = {"ok": False, "type": type(error).__name__}
    checks["cases"] = {"ok": cases_ok, "count": case_count}
    try:
        from .tool_catalog import tool_schema_sha256

        schema_hash = tool_schema_sha256()
        schema_ok = len(schema_hash) == 64
    except Exception:
        schema_hash = None
        schema_ok = False
    checks["tool_schema"] = {"ok": schema_ok, "sha256": schema_hash}
    checks["live_configuration"] = {
        "ok": False,
        "required_for_offline_commands": False,
        "note": "not inspected to avoid accessing or reporting credentials",
    }
    fatal_names = {
        "python",
        "google_genai",
        "pydantic",
        "python_dotenv",
        "pytest",
        "project_files",
        "cases",
        "tool_schema",
    }
    overall = all(checks[name]["ok"] for name in fatal_names)
    _print_json({"ok": overall, "checks": checks})
    return 0 if overall else 1


def _run_one(
    settings: Settings,
    case_id: str,
    profile: str,
    repetition: int,
    experiment_id: str,
    live: bool,
):
    from .client import GeminiInteractionsClient
    from .experiment import ExperimentRunner

    runner = ExperimentRunner(settings)
    if live:
        if not settings.allow_network:
            raise ValueError("live execution safety gate is disabled")
        client = GeminiInteractionsClient.from_environment()
        return runner.run_case(
            case_id, profile, repetition, experiment_id, mode="live", client=client
        )
    return runner.run_case(
        case_id, profile, repetition, experiment_id, mode="dry_run"
    )


def _dry_run(settings: Settings, args: argparse.Namespace) -> int:
    from .experiment import new_experiment_id

    record = _run_one(
        settings,
        args.case_id,
        args.profile,
        repetition=1,
        experiment_id=new_experiment_id(),
        live=False,
    )
    _print_json(_safe_run_view(record))
    return 0


def _run_command(settings: Settings, args: argparse.Namespace) -> int:
    from .experiment import new_experiment_id
    from .recorder import JsonlRecorder, new_artifact_path

    record = _run_one(
        settings,
        args.case_id,
        args.profile,
        repetition=1,
        experiment_id=new_experiment_id(),
        live=args.live,
    )
    path = new_artifact_path(settings.logs_dir, "run", ".jsonl")
    with JsonlRecorder(path) as recorder:
        recorder.append(record)
    result = _safe_run_view(record)
    result["raw_log"] = str(path.relative_to(settings.project_root))
    _print_json(result)
    return 0


def _batch(settings: Settings, args: argparse.Namespace) -> int:
    from .client import GeminiInteractionsClient
    from .experiment import ExperimentRunner, new_experiment_id
    from .recorder import JsonlRecorder, new_artifact_path

    experiment_id = new_experiment_id()
    runner = ExperimentRunner(settings)
    profiles = args.profile or ["baseline", "hardened"]
    total = len(runner.case_ids) * len(profiles) * args.repetitions
    if args.live:
        if not settings.allow_network:
            raise ValueError("live execution safety gate is disabled")
        if args.max_requests is None or total > args.max_requests:
            raise ValueError("live batch exceeds the explicit request limit")
        if args.request_interval_seconds is None:
            raise ValueError("live batch requires an explicit request interval")
        client = GeminiInteractionsClient.from_environment()
        mode = "live"
    else:
        client = None
        mode = "dry_run"
    path = new_artifact_path(settings.logs_dir, "batch", ".jsonl")
    completed = 0
    with JsonlRecorder(path) as recorder:
        for repetition in range(1, args.repetitions + 1):
            for profile in profiles:
                for case_id in runner.case_ids:
                    if mode == "live" and completed:
                        time.sleep(args.request_interval_seconds)
                    record = runner.run_case(
                        case_id,
                        profile,
                        repetition,
                        experiment_id,
                        mode=mode,
                        client=client,
                    )
                    recorder.append(record)
                    completed += 1
    _print_json(
        {
            "experiment_id": experiment_id,
            "execution_mode": mode,
            "records": completed,
            "raw_log": str(path.relative_to(settings.project_root)),
        }
    )
    return 0


def _inside_directory(path: Path, directory: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(directory.resolve(strict=True))
        return True
    except (ValueError, FileNotFoundError):
        return False


def _summarize(settings: Settings, args: argparse.Namespace) -> int:
    from .recorder import new_artifact_path
    from .summarizer import (
        load_raw_records,
        summarize_records,
        write_summary_exclusive,
    )

    raw_path = Path(args.log)
    if not raw_path.is_absolute():
        raw_path = settings.project_root / raw_path
    if not _inside_directory(raw_path, settings.logs_dir):
        raise ValueError("raw log must be inside artifacts/logs")
    summary = summarize_records(load_raw_records(raw_path))
    output = new_artifact_path(settings.summaries_dir, "summary", ".json")
    write_summary_exclusive(summary, output)
    _print_json(
        {
            "summary": str(output.relative_to(settings.project_root)),
            "record_count": summary["record_count"],
            "group_count": len(summary["groups"]),
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gemini-injection-lab")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")

    dry = subparsers.add_parser("dry-run")
    dry.add_argument("case_id")
    dry.add_argument("--profile", choices=["baseline", "hardened"], default="baseline")

    run = subparsers.add_parser("run")
    run.add_argument("case_id")
    run.add_argument("--profile", choices=["baseline", "hardened"], default="baseline")
    run.add_argument("--live", action="store_true")

    batch = subparsers.add_parser("batch")
    batch.add_argument("--profile", action="append", choices=["baseline", "hardened"])
    batch.add_argument("--repetitions", type=int, default=1)
    batch.add_argument("--live", action="store_true")
    batch.add_argument("--max-requests", type=int)
    batch.add_argument("--request-interval-seconds", type=float)

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("log")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    from .config import Settings

    try:
        settings = Settings.load()
        if args.command == "doctor":
            return _doctor(settings.project_root)
        if args.command == "dry-run":
            return _dry_run(settings, args)
        if args.command == "run":
            return _run_command(settings, args)
        if args.command == "batch":
            if args.repetitions < 1:
                raise ValueError("repetitions must be one or greater")
            if (
                args.request_interval_seconds is not None
                and not 0 <= args.request_interval_seconds <= 60
            ):
                raise ValueError("request interval must be between 0 and 60 seconds")
            return _batch(settings, args)
        if args.command == "summarize":
            return _summarize(settings, args)
    except (ValueError, KeyError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

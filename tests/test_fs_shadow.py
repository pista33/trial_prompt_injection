from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path

import pytest

from agent_risk_lab.cli import live_record
from agent_risk_lab.core.experiments import ExperimentRegistry
from agent_risk_lab.core.hashing import sha256_file, tree_hash
from agent_risk_lab.core.models import CommonFunctionCall, CommonInteractionResult
from agent_risk_lab.experiments.fs_shadow import execute_file_copy, shadow_workspace
from agent_risk_lab.experiments.runner import ExperimentRunner
from agent_risk_lab.providers.gemini import GeminiProviderAdapter


ROOT = Path(__file__).parents[1]
EXPERIMENT_ROOT = ROOT / "data/experiments/EXP_FILE_COPY"
FIXTURE = EXPERIMENT_ROOT / "fixture"


def test_registered_file_copy_experiment_hashes_match() -> None:
    experiment = ExperimentRegistry(ROOT / "data/experiments").get("EXP_FILE_COPY")

    assert experiment.type == "fs_shadow"
    assert experiment.prompt_sha256 == sha256_file(EXPERIMENT_ROOT / "prompt.txt")
    assert experiment.fixture_sha256 == tree_hash(FIXTURE)
    assert experiment.copy_source == "documents/source.txt"
    assert experiment.copy_destination == "archive/source_copy.txt"
    assert (FIXTURE / "documents/source.txt").read_text(encoding="utf-8") == (
        "This is a test document for an isolated file-operation experiment.\n"
    )


def test_shadow_copy_adds_only_destination_and_preserves_source() -> None:
    fixture_before = tree_hash(FIXTURE)
    source_before = (FIXTURE / "documents/source.txt").read_bytes()

    with shadow_workspace(FIXTURE) as shadow:
        before_paths = {path.relative_to(shadow).as_posix() for path in shadow.rglob("*")}
        result = execute_file_copy(
            shadow,
            {
                "source": "documents/source.txt",
                "destination": "archive/source_copy.txt",
            },
            "documents/source.txt",
            "archive/source_copy.txt",
        )
        after_paths = {path.relative_to(shadow).as_posix() for path in shadow.rglob("*")}

        assert shadow != FIXTURE
        assert after_paths - before_paths == {"archive/source_copy.txt"}
        assert (shadow / "documents/source.txt").read_bytes() == source_before
        assert (shadow / "archive/source_copy.txt").read_bytes() == source_before
        assert result["source_sha256"] == result["destination_sha256"]

    assert tree_hash(FIXTURE) == fixture_before
    assert not (FIXTURE / "archive/source_copy.txt").exists()


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        ("../outside.txt", "archive/source_copy.txt"),
        ("documents/source.txt", "/tmp/source_copy.txt"),
        ("documents/source.txt", "../source_copy.txt"),
        ("documents/source.txt", "C:\\outside\\source_copy.txt"),
        ("documents/source.txt", "..\\outside\\source_copy.txt"),
    ],
)
def test_file_copy_rejects_unsafe_paths(
    tmp_path: Path, source: str, destination: str
) -> None:
    shadow = tmp_path / "shadow"
    (shadow / "documents").mkdir(parents=True)
    (shadow / "archive").mkdir()
    (shadow / "documents/source.txt").write_text("safe\n", encoding="utf-8")

    with pytest.raises(ValueError):
        execute_file_copy(
            shadow,
            {"source": source, "destination": destination},
            source,
            destination,
        )


def test_file_copy_rejects_symlink_and_overwrite(tmp_path: Path) -> None:
    shadow = tmp_path / "shadow"
    (shadow / "documents").mkdir(parents=True)
    (shadow / "archive").mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (shadow / "documents/source.txt").symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        execute_file_copy(
            shadow,
            {"source": "documents/source.txt", "destination": "archive/copy.txt"},
            "documents/source.txt",
            "archive/copy.txt",
        )

    (shadow / "documents/source.txt").unlink()
    (shadow / "documents/source.txt").write_text("source\n", encoding="utf-8")
    (shadow / "archive/copy.txt").write_text("existing\n", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite rejected"):
        execute_file_copy(
            shadow,
            {"source": "documents/source.txt", "destination": "archive/copy.txt"},
            "documents/source.txt",
            "archive/copy.txt",
        )


def test_fixture_symlink_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "experiments"
    fixture = root / "EXP/fixture"
    (fixture / "documents").mkdir(parents=True)
    (fixture / "archive").mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (fixture / "documents/source.txt").symlink_to(outside)
    prompt = root / "EXP/prompt.txt"
    prompt.write_text("copy\n", encoding="utf-8")
    (root / "registry.toml").write_text(
        f'''schema_version = "1"
[[experiments]]
id = "EXP"
type = "fs_shadow"
description = "copy"
prompt_file = "EXP/prompt.txt"
prompt_sha256 = "{hashlib.sha256(prompt.read_bytes()).hexdigest()}"
fixture_root = "EXP/fixture"
fixture_sha256 = "{'0' * 64}"
copy_source = "documents/source.txt"
copy_destination = "archive/copy.txt"
enabled = true
''',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid registered fixture path"):
        ExperimentRegistry(root).get("EXP")


@pytest.mark.parametrize("fixture_root", ["/tmp/outside", "../outside"])
def test_unsafe_fixture_root_is_rejected(tmp_path: Path, fixture_root: str) -> None:
    root = tmp_path / "experiments"
    experiment_root = root / "EXP"
    experiment_root.mkdir(parents=True)
    prompt = experiment_root / "prompt.txt"
    prompt.write_text("copy\n", encoding="utf-8")
    (root / "registry.toml").write_text(
        f'''schema_version = "1"
[[experiments]]
id = "EXP"
type = "fs_shadow"
description = "copy"
prompt_file = "EXP/prompt.txt"
prompt_sha256 = "{hashlib.sha256(prompt.read_bytes()).hexdigest()}"
fixture_root = "{fixture_root}"
fixture_sha256 = "{'0' * 64}"
copy_source = "documents/source.txt"
copy_destination = "archive/copy.txt"
enabled = true
''',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid registered fixture path"):
        ExperimentRegistry(root).get("EXP")


def test_dry_run_has_tool_and_never_calls_adapter() -> None:
    called = False

    def adapter_factory():
        nonlocal called
        called = True
        raise AssertionError("dry-run must not create an adapter")

    run = ExperimentRunner(ROOT).run(
        "EXP_FILE_COPY", "baseline", live=False, adapter_factory=adapter_factory
    )

    assert called is False
    assert run["execution_mode"] == "dry_run"
    assert run["request"].experiment_type == "fs_shadow"
    assert [tool["name"] for tool in run["request"].tools] == ["file_copy"]
    assert "additionalProperties" not in run["request"].tools[0]["parameters"]
    assert run["metadata"]["profile"].resolved_version == 1
    assert run["result"] is None
    assert run["evaluation"] is None
    assert run["tool_execution"] is None


def test_mock_live_executes_once_in_destroyed_shadow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_before = tree_hash(FIXTURE)
    observed_shadow: Path | None = None
    from agent_risk_lab.experiments import runner as runner_module

    original = runner_module.shadow_workspace

    @contextmanager
    def observed(fixture: Path):
        nonlocal observed_shadow
        with original(fixture) as shadow:
            observed_shadow = shadow
            yield shadow

    monkeypatch.setattr(runner_module, "shadow_workspace", observed)
    monkeypatch.setenv("GEMINI_ALLOW_NETWORK", "1")

    class Adapter:
        def create_once(self, request):
            return CommonInteractionResult(
                provider_id=request.provider_id,
                requested_model=request.requested_model,
                returned_model=request.requested_model,
                function_calls=[
                    CommonFunctionCall(
                        0,
                        "file_copy",
                        {
                            "source": "documents/source.txt",
                            "destination": "archive/source_copy.txt",
                        },
                    )
                ],
            )

    run = ExperimentRunner(ROOT).run(
        "EXP_FILE_COPY",
        "baseline",
        live=True,
        adapter_factory=lambda: Adapter(),
    )

    assert run["tool_execution"]["status"] == "succeeded"
    assert run["evaluation"]["passed"] is True
    record = live_record(ROOT, run)
    assert record["registered_fixture_sha256"] == tree_hash(FIXTURE)
    assert record["tool_execution"]["status"] == "succeeded"
    assert run["filesystem_unchanged"] is True
    assert tree_hash(FIXTURE) == fixture_before
    assert observed_shadow is not None and not observed_shadow.exists()


def test_mock_gemini_interaction_calls_api_once_and_executes_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Interactions:
        def __init__(self) -> None:
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "status": "completed",
                "model": "gemini-3.1-flash-lite",
                "steps": [
                    {
                        "type": "function_call",
                        "name": "file_copy",
                        "arguments": {
                            "source": "documents/source.txt",
                            "destination": "archive/source_copy.txt",
                        },
                    }
                ],
            }

    class SDK:
        def __init__(self) -> None:
            self.interactions = Interactions()

    sdk = SDK()
    monkeypatch.setenv("GEMINI_ALLOW_NETWORK", "1")
    run = ExperimentRunner(ROOT).run(
        "EXP_FILE_COPY",
        "baseline",
        live=True,
        adapter_factory=lambda: GeminiProviderAdapter(sdk),
    )

    assert len(sdk.interactions.calls) == 1
    request = sdk.interactions.calls[0]
    assert request["store"] is False
    assert "previous_interaction_id" not in request
    assert [tool["name"] for tool in request["tools"]] == ["file_copy"]
    assert run["tool_execution"]["status"] == "succeeded"
    assert run["evaluation"]["passed"] is True

from __future__ import annotations

import base64
import os
from pathlib import Path

from agent_risk_lab.core.experiments import ExperimentRegistry
from agent_risk_lab.core.hashing import sha256_bytes, sha256_file, tree_hash
from agent_risk_lab.core.models import CommonInteractionRequest
from agent_risk_lab.core.paths import safe_path
from agent_risk_lab.core.profiles import (
    ProfileLoader,
    ResolvedProfile,
    compose_effective_prompt,
    normalize,
)
from agent_risk_lab.core.targets import TargetLoader
from agent_risk_lab.core.tools import file_copy_declaration
from agent_risk_lab.evaluators.fs_shadow import evaluate_file_copy
from agent_risk_lab.evaluators.prompt import evaluate_prompt
from agent_risk_lab.experiments.fs_shadow import (
    build_snapshot,
    execute_file_copy,
    shadow_workspace,
)


class ExperimentRunner:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root

    def prepare(
        self,
        experiment_id: str,
        profile_id: str,
        target_id: str = "gemini_3_1_flash_lite",
        profile_version: int | None = None,
        resolved_profile: ResolvedProfile | None = None,
    ):
        target, provider = TargetLoader(
            self.root / "configs/providers", self.root / "configs/targets"
        ).load_target(target_id)
        registry = ExperimentRegistry(self.root / "data/experiments")
        experiment = registry.get(experiment_id, verify=True)
        loaded_inputs = registry.read_inputs(experiment)
        profile = resolved_profile or ProfileLoader(self.root / "configs/profiles").load_profile(
            profile_id, profile_version
        )
        if profile.name != profile_id or (
            resolved_profile is not None
            and profile_version not in (None, profile.requested_version)
        ):
            raise ValueError("resolved profile does not match requested profile")

        base = normalize((self.root / "configs/base_system_prompt.txt").read_text(encoding="utf-8"))
        system = compose_effective_prompt(base, profile.compiled_profile_prompt)
        parts = []
        for registered, data, mime in loaded_inputs:
            if registered.type == "document":
                parts.append(
                    {
                        "type": "document",
                        "mime_type": mime,
                        "data": base64.b64encode(data).decode("ascii"),
                    }
                )
            else:
                parts.append({"type": "text", "text": data.decode("utf-8")})

        input_value = (
            parts[0]["text"]
            if len(parts) == 1 and parts[0]["type"] == "text"
            else parts
        )
        tools = []
        fixture_path = None
        fixture_before = None
        if experiment.type == "fs_shadow":
            fixture_path = safe_path(
                self.root / "data/experiments", experiment.fixture_root or "", "directory"
            )
            fixture_before = tree_hash(fixture_path)
            input_value = [
                parts[0],
                {
                    "type": "text",
                    "text": "FileSystemSnapshot:\n" + build_snapshot(fixture_path),
                },
            ]
            tools = [
                file_copy_declaration(
                    experiment.copy_source or "", experiment.copy_destination or ""
                )
            ]

        request = CommonInteractionRequest(
            target.provider_id,
            target.model,
            experiment_id,
            experiment.type,
            profile.id,
            profile.version,
            profile.sha256,
            sha256_bytes(system.encode()),
            system,
            input_value,
            tools,
            False,
        )
        metadata = {
            "experiment": experiment,
            "profile": profile,
            "target": target,
            "provider": provider,
            "base_sha": sha256_bytes(base.encode()),
            "fixture_path": fixture_path,
            "fixture_before": fixture_before,
        }
        return request, metadata

    def prepare_batch(
        self,
        experiment_ids: list[str],
        profile_id: str,
        target_id: str = "gemini_3_1_flash_lite",
        profile_version: int | None = None,
    ):
        """Resolve a profile once, then pin that object across every batch case."""
        profile = ProfileLoader(self.root / "configs/profiles").load_profile(
            profile_id, profile_version
        )
        return [
            self.prepare(experiment_id, profile_id, target_id, profile_version, profile)
            for experiment_id in experiment_ids
        ]

    def run(
        self,
        experiment_id,
        profile_id,
        live=False,
        target_id="gemini_3_1_flash_lite",
        adapter_factory=None,
        profile_version: int | None = None,
    ):
        request, metadata = self.prepare(
            experiment_id, profile_id, target_id, profile_version
        )
        if not live:
            return {
                "execution_mode": "dry_run",
                "request": request,
                "metadata": metadata,
                "result": None,
                "evaluation": None,
                "tool_execution": None,
                "filesystem_unchanged": True,
            }

        target = metadata["target"]
        if target.adapter_id != "gemini":
            raise ValueError("unknown adapter")
        if os.getenv(target.network_permission_env) != "1":
            raise ValueError(
                f"live execution requires --live and {target.network_permission_env}=1"
            )
        if adapter_factory is None:
            from agent_risk_lab.providers.gemini import GeminiProviderAdapter

            adapter_factory = GeminiProviderAdapter.from_environment
        result = adapter_factory().create_once(request)

        experiment = metadata["experiment"]
        tool_execution = None
        if experiment.type == "fs_shadow":
            fixture = metadata["fixture_path"]
            fixture_before = metadata["fixture_before"]
            source_before = sha256_file(safe_path(fixture, experiment.copy_source or ""))
            if len(result.function_calls) == 1 and result.function_calls[0].name == "file_copy":
                with shadow_workspace(fixture) as shadow:
                    shadow_before = tree_hash(shadow)
                    try:
                        tool_execution = execute_file_copy(
                            shadow,
                            result.function_calls[0].arguments,
                            experiment.copy_source or "",
                            experiment.copy_destination or "",
                        )
                    except ValueError as error:
                        tool_execution = {
                            "tool": "file_copy",
                            "status": "rejected",
                            "error": str(error),
                        }
                    except OSError:
                        tool_execution = {
                            "tool": "file_copy",
                            "status": "rejected",
                            "error": "file_copy I/O error",
                        }
                    tool_execution["shadow_before_sha256"] = shadow_before
                    tool_execution["shadow_after_sha256"] = tree_hash(shadow)
                    source_unchanged = (
                        sha256_file(safe_path(shadow, experiment.copy_source or ""))
                        == source_before
                    )
            else:
                source_unchanged = True
            fixture_unchanged = tree_hash(fixture) == fixture_before
            evaluation = evaluate_file_copy(
                result.function_calls,
                tool_execution,
                source_unchanged,
                fixture_unchanged,
            )
        else:
            fixture_unchanged = True
            evaluation = evaluate_prompt(result.response_text, result.function_calls)

        return {
            "execution_mode": "live",
            "request": request,
            "metadata": metadata,
            "result": result,
            "evaluation": evaluation,
            "tool_execution": tool_execution,
            "filesystem_unchanged": fixture_unchanged,
        }

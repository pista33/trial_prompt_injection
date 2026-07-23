from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_bytes
from .paths import read_prompt, safe_path, safe_relative


SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class ExperimentInput:
    type: str
    file: str
    sha256: str


@dataclass(frozen=True)
class Experiment:
    id: str
    type: str
    description: str
    enabled: bool
    inputs: tuple[ExperimentInput, ...]
    # Legacy single-input registry fields remain readable for compatibility.
    prompt_file: str | None = None
    prompt_sha256: str | None = None
    fixture_root: str | None = None
    fixture_sha256: str | None = None
    copy_source: str | None = None
    copy_destination: str | None = None


class ExperimentRegistry:
    """The registry is the sole allowlist for executable experiment files."""

    def __init__(self, root: Path, registry: Path | None = None) -> None:
        self.root = root
        self.registry = registry or root / "registry.toml"

    def _parse_inputs(self, raw: dict[str, object], experiment_id: str) -> tuple[ExperimentInput, ...]:
        raw_inputs = raw.get("inputs")
        prompt_file = raw.get("prompt_file")
        prompt_sha256 = raw.get("prompt_sha256")
        if raw_inputs is not None and (prompt_file is not None or prompt_sha256 is not None):
            raise ValueError(
                f"experiment {experiment_id!r} must use either inputs or prompt_file, not both"
            )
        if raw_inputs is None:
            if not isinstance(prompt_file, str) or not isinstance(prompt_sha256, str):
                raise ValueError(f"experiment {experiment_id!r} has no registered inputs")
            input_type = "document" if Path(prompt_file).suffix.lower() == ".pdf" else "text"
            raw_inputs = [{"type": input_type, "file": prompt_file, "sha256": prompt_sha256}]
        if not isinstance(raw_inputs, list) or not raw_inputs:
            raise ValueError(f"experiment {experiment_id!r} inputs must be a non-empty list")
        inputs: list[ExperimentInput] = []
        for index, item in enumerate(raw_inputs):
            if not isinstance(item, dict) or set(item) != {"type", "file", "sha256"}:
                raise ValueError(f"invalid input #{index} for experiment {experiment_id!r}")
            input_type = item.get("type")
            file = item.get("file")
            sha256 = item.get("sha256")
            if input_type not in {"text", "document"}:
                raise ValueError(
                    f"unknown input type for experiment {experiment_id!r} input #{index}: {input_type!r}"
                )
            if not isinstance(file, str) or not file:
                raise ValueError(f"invalid file for experiment {experiment_id!r} input #{index}")
            if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
                raise ValueError(f"invalid sha256 for experiment {experiment_id!r} input #{index}")
            inputs.append(ExperimentInput(input_type, file, sha256))
        return tuple(inputs)

    def all(self) -> list[Experiment]:
        try:
            data = tomllib.loads(self.registry.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ValueError(f"experiment registry does not exist: {self.registry}") from error
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            raise ValueError(f"invalid experiment registry TOML: {self.registry}") from error
        if data.get("schema_version") != "1":
            raise ValueError(f"unsupported experiment registry schema: {self.registry}")
        raw_experiments = data.get("experiments", [])
        if not isinstance(raw_experiments, list):
            raise ValueError(f"experiments must be a list: {self.registry}")
        result: list[Experiment] = []
        seen: set[str] = set()
        for raw in raw_experiments:
            if not isinstance(raw, dict):
                raise ValueError(f"invalid experiment entry: {self.registry}")
            experiment_id = raw.get("id")
            if not isinstance(experiment_id, str) or not experiment_id:
                raise ValueError(f"invalid experiment ID: {self.registry}")
            if experiment_id in seen:
                raise ValueError(f"duplicate experiment ID {experiment_id!r}: {self.registry}")
            seen.add(experiment_id)
            experiment_type = raw.get("type")
            if experiment_type not in {"prompt", "fs_shadow"}:
                raise ValueError(f"unknown experiment type for {experiment_id!r}: {self.registry}")
            description = raw.get("description")
            enabled = raw.get("enabled")
            if not isinstance(description, str):
                raise ValueError(f"invalid description for experiment {experiment_id!r}")
            if not isinstance(enabled, bool):
                raise ValueError(f"enabled must be boolean for experiment {experiment_id!r}")
            inputs = self._parse_inputs(raw, experiment_id)
            fixture_root = raw.get("fixture_root")
            fixture_sha256 = raw.get("fixture_sha256")
            copy_source = raw.get("copy_source")
            copy_destination = raw.get("copy_destination")
            if experiment_type == "fs_shadow":
                if len(inputs) != 1 or inputs[0].type != "text":
                    raise ValueError(f"fs_shadow experiment {experiment_id!r} requires one text input")
                if not isinstance(fixture_root, str) or not fixture_root:
                    raise ValueError(f"fixture_root is required for experiment {experiment_id!r}")
                if not isinstance(fixture_sha256, str) or not SHA256_RE.fullmatch(fixture_sha256):
                    raise ValueError(f"invalid fixture_sha256 for experiment {experiment_id!r}")
                if not isinstance(copy_source, str) or not isinstance(copy_destination, str):
                    raise ValueError(f"copy policy is required for experiment {experiment_id!r}")
                try:
                    source_relative = safe_relative(copy_source)
                    destination_relative = safe_relative(copy_destination)
                except ValueError as error:
                    raise ValueError(f"unsafe copy policy for experiment {experiment_id!r}") from error
                if source_relative == destination_relative:
                    raise ValueError(f"copy source and destination must differ for experiment {experiment_id!r}")
            elif any(
                item is not None
                for item in (fixture_root, fixture_sha256, copy_source, copy_destination)
            ):
                raise ValueError(f"fixture fields are only valid for fs_shadow experiment {experiment_id!r}")
            allowed = {
                "id", "type", "description", "enabled", "inputs",
                "prompt_file", "prompt_sha256", "fixture_root", "fixture_sha256",
                "copy_source", "copy_destination",
            }
            unknown = set(raw) - allowed
            if unknown:
                raise ValueError(f"unknown fields for experiment {experiment_id!r}: {sorted(unknown)}")
            result.append(
                Experiment(
                    id=experiment_id,
                    type=experiment_type,
                    description=description,
                    enabled=enabled,
                    inputs=inputs,
                    prompt_file=raw.get("prompt_file") if isinstance(raw.get("prompt_file"), str) else None,
                    prompt_sha256=(
                        raw.get("prompt_sha256")
                        if isinstance(raw.get("prompt_sha256"), str)
                        else None
                    ),
                    fixture_root=fixture_root if isinstance(fixture_root, str) else None,
                    fixture_sha256=fixture_sha256 if isinstance(fixture_sha256, str) else None,
                    copy_source=copy_source if isinstance(copy_source, str) else None,
                    copy_destination=copy_destination if isinstance(copy_destination, str) else None,
                )
            )
        return result

    def read_inputs(self, experiment: Experiment) -> tuple[tuple[ExperimentInput, bytes, str], ...]:
        loaded: list[tuple[ExperimentInput, bytes, str]] = []
        for index, registered in enumerate(experiment.inputs):
            try:
                path = safe_path(self.root, registered.file)
                data, mime = read_prompt(path)
            except (FileNotFoundError, ValueError, OSError) as error:
                raise ValueError(
                    f"invalid registered input path for experiment {experiment.id!r} "
                    f"input #{index}: {registered.file!r}"
                ) from error
            expected_mime = "text/plain" if registered.type == "text" else "application/pdf"
            if mime != expected_mime:
                raise ValueError(
                    f"registered input type mismatch for experiment {experiment.id!r} "
                    f"input #{index}: expected {registered.type!r}"
                )
            actual_sha256 = sha256_bytes(data)
            if actual_sha256 != registered.sha256:
                raise ValueError(
                    f"registered input SHA-256 mismatch for experiment {experiment.id!r} "
                    f"input #{index}: expected {registered.sha256}, got {actual_sha256}"
                )
            loaded.append((registered, data, mime))
        return tuple(loaded)

    def get(self, experiment_id: str, verify: bool = True) -> Experiment:
        found = next((experiment for experiment in self.all() if experiment.id == experiment_id), None)
        if found is None:
            raise ValueError(f"unregistered experiment ID: {experiment_id}")
        if not found.enabled:
            raise ValueError(f"experiment is disabled: {experiment_id}")
        if verify:
            self.read_inputs(found)
            if found.type == "fs_shadow":
                try:
                    fixture = safe_path(self.root, found.fixture_root or "", "directory")
                    source = safe_path(fixture, found.copy_source or "")
                    destination = fixture.joinpath(*(safe_relative(found.copy_destination or "").parts))
                    destination_parent = safe_path(
                        fixture,
                        str(safe_relative(found.copy_destination or "").parent),
                        "directory",
                    )
                except (FileNotFoundError, ValueError, OSError) as error:
                    raise ValueError(
                        f"invalid registered fixture path for experiment {experiment_id!r}"
                    ) from error
                if not source.is_file() or destination.exists() or destination.is_symlink():
                    raise ValueError(f"invalid copy policy state for experiment {experiment_id!r}")
                if not destination_parent.is_dir():
                    raise ValueError(f"invalid copy destination for experiment {experiment_id!r}")
                from .hashing import tree_hash

                actual_fixture_sha256 = tree_hash(fixture)
                if actual_fixture_sha256 != found.fixture_sha256:
                    raise ValueError(
                        f"registered fixture SHA-256 mismatch for experiment {experiment_id!r}: "
                        f"expected {found.fixture_sha256}, got {actual_fixture_sha256}"
                    )
        return found

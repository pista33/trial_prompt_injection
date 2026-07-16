from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_bytes, tree_hash
from .paths import read_prompt, safe_path


@dataclass(frozen=True)
class Experiment:
    id: str
    type: str
    description: str
    prompt_file: str
    prompt_sha256: str
    enabled: bool
    fixture_root: str | None = None
    fixture_sha256: str | None = None


class ExperimentRegistry:
    """The registry is the sole allowlist for executable experiment files."""

    def __init__(self, root: Path, registry: Path | None = None) -> None:
        self.root = root
        self.registry = registry or root / "registry.toml"

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
            if raw.get("type") not in {"prompt", "fs_shadow"}:
                raise ValueError(f"unknown experiment type for {experiment_id!r}: {self.registry}")
            try:
                experiment = Experiment(**raw)
            except TypeError as error:
                raise ValueError(
                    f"invalid fields for experiment {experiment_id!r}: {self.registry}"
                ) from error
            if not isinstance(experiment.enabled, bool):
                raise ValueError(f"enabled must be boolean for experiment {experiment_id!r}")
            if not isinstance(experiment.prompt_sha256, str) or len(experiment.prompt_sha256) != 64:
                raise ValueError(f"invalid prompt_sha256 for experiment {experiment_id!r}")
            if experiment.type == "fs_shadow" and (
                not experiment.fixture_root or not experiment.fixture_sha256
            ):
                raise ValueError(f"fixture metadata is required for experiment {experiment_id!r}")
            result.append(experiment)
        return result

    def get(self, experiment_id: str, verify: bool = True) -> Experiment:
        found = next((experiment for experiment in self.all() if experiment.id == experiment_id), None)
        if found is None:
            raise ValueError(f"unregistered experiment ID: {experiment_id}")
        if not found.enabled:
            raise ValueError(f"experiment is disabled: {experiment_id}")
        if verify:
            try:
                prompt = safe_path(self.root, found.prompt_file)
            except (FileNotFoundError, ValueError, OSError) as error:
                raise ValueError(
                    f"invalid registered prompt path for experiment {experiment_id!r}: {found.prompt_file!r}"
                ) from error
            data, _ = read_prompt(prompt)
            actual_prompt_sha256 = sha256_bytes(data)
            if actual_prompt_sha256 != found.prompt_sha256:
                raise ValueError(
                    f"registered prompt SHA-256 mismatch for experiment {experiment_id!r}: "
                    f"expected {found.prompt_sha256}, got {actual_prompt_sha256}"
                )
            if found.type == "fs_shadow":
                try:
                    fixture = safe_path(self.root, found.fixture_root or "", "directory")
                except (FileNotFoundError, ValueError, OSError) as error:
                    raise ValueError(
                        f"invalid registered fixture path for experiment {experiment_id!r}: "
                        f"{found.fixture_root!r}"
                    ) from error
                actual_fixture_sha256 = tree_hash(fixture)
                if actual_fixture_sha256 != found.fixture_sha256:
                    raise ValueError(
                        f"registered fixture SHA-256 mismatch for experiment {experiment_id!r}: "
                        f"expected {found.fixture_sha256}, got {actual_fixture_sha256}"
                    )
        return found

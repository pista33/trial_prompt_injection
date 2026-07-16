from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_risk_lab.core.experiments import ExperimentRegistry


def _registry(prompt_file: str, digest: str, enabled: bool = True) -> str:
    return f'''schema_version = "1"
[[experiments]]
id = "EXP-1"
type = "prompt"
description = "registered"
prompt_file = "{prompt_file}"
prompt_sha256 = "{digest}"
enabled = {str(enabled).lower()}
'''


def _setup(tmp_path: Path, registry: str, prompt: bytes | None = b"registered\n") -> ExperimentRegistry:
    (tmp_path / "registry.toml").write_text(registry, encoding="utf-8")
    if prompt is not None:
        path = tmp_path / "EXP-1/prompt.txt"
        path.parent.mkdir()
        path.write_bytes(prompt)
    return ExperimentRegistry(tmp_path)


def test_empty_registry(tmp_path: Path) -> None:
    assert _setup(tmp_path, 'schema_version = "1"\n', None).all() == []


@pytest.mark.parametrize(
    "value",
    [
        "bad = [",
        'schema_version="1"\n[[experiments]]\nid="x"\ntype="bad"\n'
        'description="x"\nprompt_file="x"\nprompt_sha256="' + "0" * 64 + '"\nenabled=true\n',
        'schema_version="1"\n[[experiments]]\nid="x"\ntype="prompt"\n'
        'description="x"\nprompt_file="x"\napproved=true\n'
        'approved_prompt_sha256="' + "0" * 64 + '"\nenabled=true\n',
    ],
)
def test_invalid_registry(value: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _setup(tmp_path, value, None).all()


def test_registered_prompt_is_verified(tmp_path: Path) -> None:
    content = b"registered\n"
    digest = hashlib.sha256(content).hexdigest()
    experiment = _setup(tmp_path, _registry("EXP-1/prompt.txt", digest)).get("EXP-1")
    assert experiment.prompt_sha256 == digest


def test_unregistered_experiment_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unregistered experiment ID: NO"):
        _setup(tmp_path, 'schema_version = "1"\n', None).get("NO")


def test_disabled_experiment_is_rejected(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"registered\n").hexdigest()
    with pytest.raises(ValueError, match="experiment is disabled: EXP-1"):
        _setup(tmp_path, _registry("EXP-1/prompt.txt", digest, enabled=False)).get("EXP-1")


def test_missing_prompt_is_rejected_before_execution(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid registered prompt path.*EXP-1/prompt.txt"):
        _setup(tmp_path, _registry("EXP-1/prompt.txt", "0" * 64), None).get("EXP-1")


@pytest.mark.parametrize("name", ["../outside.txt", "/tmp/outside.txt"])
def test_unsafe_registry_path_is_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="invalid registered prompt path"):
        _setup(tmp_path, _registry(name, "0" * 64), None).get("EXP-1")


def test_external_symlink_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    registry = _setup(tmp_path, _registry("EXP-1/prompt.txt", "0" * 64), None)
    directory = tmp_path / "EXP-1"
    directory.mkdir()
    (directory / "prompt.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="invalid registered prompt path"):
        registry.get("EXP-1")


def test_prompt_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="registered prompt SHA-256 mismatch.*EXP-1"):
        _setup(tmp_path, _registry("EXP-1/prompt.txt", "0" * 64)).get("EXP-1")

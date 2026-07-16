from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_risk_lab.cli import live_record, main
from agent_risk_lab.core.models import CommonInteractionResult
from agent_risk_lab.core.profiles import ProfileLoader, compose_effective_prompt, normalize
from agent_risk_lab.experiments.runner import ExperimentRunner


ROOT = Path(__file__).parents[1]


def _profile_text(
    name: str = "baseline",
    version: int = 1,
    fragments: str = "[]",
    status: str = "published",
) -> str:
    return (
        f'name = "{name}"\nversion = {version}\nstatus = "{status}"\n'
        'description = "description"\nchange_summary = "summary"\n'
        f"fragments = {fragments}\n"
    )


def _tree(
    tmp_path: Path,
    registry: str | None = None,
    profile: str | None = None,
    name: str = "baseline",
    version: int = 1,
) -> ProfileLoader:
    root = tmp_path / "profiles"
    root.mkdir()
    (root / "registry.toml").write_text(
        registry
        or 'schema_version = 1\n[profiles.baseline]\nlatest = 1\npublished = [1]\n',
        encoding="utf-8",
    )
    version_root = root / name / f"v{version}"
    version_root.mkdir(parents=True)
    (version_root / "profile.toml").write_text(
        profile or _profile_text(name, version), encoding="utf-8"
    )
    return ProfileLoader(root)


def test_registry_latest_resolves_baseline_and_hardened() -> None:
    loader = ProfileLoader(ROOT / "configs/profiles")
    assert loader.load_profile("baseline").resolved_version == 1
    assert loader.load_profile("hardened").resolved_version == 1


@pytest.mark.parametrize(
    ("registry", "message"),
    [
        (
            'schema_version = 1\n[profiles.baseline]\nlatest = 2\npublished = [1]\n',
            "latest v2 is not published",
        ),
        (
            'schema_version = 1\n[profiles.baseline]\nlatest = 1\npublished = [1, 1]\n',
            "duplicate published versions",
        ),
        (
            'schema_version = 1\n[profiles.baseline]\nlatest = 0\npublished = [0]\n',
            "positive integer",
        ),
        (
            'schema_version = 1\n[profiles.baseline]\nlatest = "1"\npublished = [1]\n',
            "latest must be a positive integer",
        ),
        (
            'schema_version = 1\n[profiles.baseline]\nlatest = 1\npublished = ["1"]\n',
            "published must be positive integers",
        ),
    ],
)
def test_invalid_registry_values(tmp_path: Path, registry: str, message: str) -> None:
    loader = _tree(tmp_path, registry=registry)
    with pytest.raises(ValueError, match=message):
        loader.load_profile("baseline")


def test_invalid_registry_toml_has_clear_error(tmp_path: Path) -> None:
    loader = _tree(tmp_path)
    (loader.root / "registry.toml").write_text("profiles = [", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid profile registry TOML.*registry.toml"):
        loader.list_profiles()


def test_invalid_profile_toml_has_clear_error(tmp_path: Path) -> None:
    loader = _tree(tmp_path, profile="name = [")
    with pytest.raises(ValueError, match="invalid profile TOML.*profile.toml"):
        loader.load_profile("baseline", 1)


def test_unknown_profile_and_version_are_rejected(tmp_path: Path) -> None:
    loader = _tree(tmp_path)
    with pytest.raises(ValueError, match="unknown profile 'missing'"):
        loader.load_profile("missing")
    with pytest.raises(ValueError, match="requested v2 is not published"):
        loader.load_profile("baseline", 2)


def test_unpublished_existing_version_is_rejected(tmp_path: Path) -> None:
    loader = _tree(tmp_path)
    draft = loader.root / "baseline/v2"
    draft.mkdir()
    (draft / "profile.toml").write_text(_profile_text(version=2), encoding="utf-8")
    with pytest.raises(ValueError, match="requested v2 is not published"):
        loader.load_profile("baseline", 2)


def test_missing_published_version_directory_is_rejected(tmp_path: Path) -> None:
    registry = 'schema_version = 1\n[profiles.baseline]\nlatest = 1\npublished = [1, 2]\n'
    loader = _tree(tmp_path, registry=registry)
    with pytest.raises(ValueError, match="published v2 is missing"):
        loader.load_profile("baseline")


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        (_profile_text(name="hardened"), "profile name mismatch"),
        (_profile_text(version=2), "profile version mismatch"),
        (_profile_text(fragments='[1]'), "fragments must be a string list"),
        (_profile_text(status="draft"), "is not published"),
    ],
)
def test_profile_toml_must_match_location(tmp_path: Path, profile: str, message: str) -> None:
    loader = _tree(tmp_path, profile=profile)
    with pytest.raises(ValueError, match=message):
        loader.load_profile("baseline", 1)


def test_requested_and_resolved_versions_are_distinct() -> None:
    loader = ProfileLoader(ROOT / "configs/profiles")
    latest = loader.load_profile("baseline")
    explicit = loader.load_profile("baseline", 1)
    assert latest.requested_version is None and latest.resolved_version == 1
    assert explicit.requested_version == 1 and explicit.resolved_version == 1


def test_baseline_and_hardened_v1_are_effectively_identical() -> None:
    loader = ProfileLoader(ROOT / "configs/profiles")
    baseline = loader.load_profile("baseline", version=1)
    hardened = loader.load_profile("hardened", version=1)
    assert baseline.compiled_profile_prompt == ""
    assert hardened.compiled_profile_prompt == ""
    assert baseline.compiled_profile_sha256 == hashlib.sha256(b"").hexdigest()
    base_instruction = "BASE INSTRUCTION\n"
    baseline_effective = compose_effective_prompt(base_instruction, baseline.compiled_profile_prompt)
    hardened_effective = compose_effective_prompt(base_instruction, hardened.compiled_profile_prompt)
    assert baseline_effective == hardened_effective == base_instruction
    assert hashlib.sha256(baseline_effective.encode()).hexdigest() == hashlib.sha256(
        hardened_effective.encode()
    ).hexdigest()


@pytest.mark.parametrize("fragment", ["../outside.txt", "/tmp/outside.txt", "missing.txt"])
def test_unsafe_or_missing_fragment_is_rejected(tmp_path: Path, fragment: str) -> None:
    loader = _tree(tmp_path, profile=_profile_text(fragments=f'[{fragment!r}]'))
    with pytest.raises(ValueError, match="fragment"):
        loader.load_profile("baseline", 1)


def test_external_fragment_symlink_is_rejected(tmp_path: Path) -> None:
    loader = _tree(tmp_path, profile=_profile_text(fragments='["link.txt"]'))
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (loader.root / "baseline/v1/link.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="fragment is a symlink"):
        loader.load_profile("baseline", 1)


def test_batch_resolves_profile_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    original = ProfileLoader.load_profile

    def counted(self: ProfileLoader, name: str, version: int | None = None):
        nonlocal calls
        calls += 1
        return original(self, name, version)

    monkeypatch.setattr(ProfileLoader, "load_profile", counted)
    prepared = ExperimentRunner(ROOT).prepare_batch(
        ["EXP-ABE-URL", "EXP-ABE-URL"], "hardened", profile_version=1
    )
    assert calls == 1
    assert prepared[0][1]["profile"] is prepared[1][1]["profile"]
    assert {item[0].profile_version for item in prepared} == {1}


def test_cli_profile_backward_compatibility_and_explicit_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in ("baseline", "hardened"):
        assert main(["experiment-run", "EXP-ABE-URL", "--profile", name]) == 0
        output = capsys.readouterr().out
        assert '"resolved_version": 1' in output
        assert f'"profile_path": "configs/profiles/{name}/v1/profile.toml"' in output
        assert str(ROOT) not in output
    assert (
        main(
            [
                "experiment-run",
                "EXP-ABE-URL",
                "--profile",
                "hardened",
                "--profile-version",
                "1",
            ]
        )
        == 0
    )
    assert '"requested_version": 1' in capsys.readouterr().out


def test_live_log_profile_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class Adapter:
        def create_once(self, request):
            return CommonInteractionResult(
                provider_id=request.provider_id,
                requested_model=request.requested_model,
                returned_model=request.requested_model,
            )

    monkeypatch.setenv("GEMINI_ALLOW_NETWORK", "1")
    run = ExperimentRunner(ROOT).run(
        "EXP-ABE-URL",
        "hardened",
        live=True,
        adapter_factory=lambda: Adapter(),
        profile_version=1,
    )
    record = live_record(ROOT, run)
    assert record["profile_name"] == "hardened"
    assert record["requested_profile_version"] == 1
    assert record["resolved_profile_version"] == 1
    assert record["profile_path"] == "configs/profiles/hardened/v1/profile.toml"
    assert record["fragment_names"] == ()
    assert record["profile_sha256"] == hashlib.sha256(b"").hexdigest()
    assert record["base_instruction_sha256"] == record["effective_system_prompt_sha256"]
    assert record["registered_prompt_sha256"] == (
        "a57b90b8d7f5be35ebe789123811d7874a0f513c5d1fc56b9c9cbb31a50b4714"
    )
    assert "approved_prompt_sha256" not in record
    assert "approved_fixture_sha256" not in record


def test_newlines() -> None:
    assert normalize("a  \r\n b\r\n\r\n") == "a\n b\n"

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_risk_lab.cli import main, parser
from agent_risk_lab.core.targets import TargetLoader
from agent_risk_lab.experiments.runner import ExperimentRunner


ROOT = Path(__file__).parents[1]


def test_registered_target_loads_and_hashes_exact_file() -> None:
    loader = TargetLoader(ROOT / "configs/providers", ROOT / "configs/targets")
    target, provider = loader.load_target("gemini_3_1_flash_lite")
    raw = (ROOT / "configs/targets/gemini_3_1_flash_lite.toml").read_bytes()

    assert target.provider_id == provider.provider_id == "gemini"
    assert target.adapter_id == provider.adapter_id == "gemini"
    assert target.model == "gemini-3.1-flash-lite"
    assert target.network_permission_env == "GEMINI_ALLOW_NETWORK"
    assert target.sha256 == hashlib.sha256(raw).hexdigest()


def test_unknown_target_is_rejected() -> None:
    loader = TargetLoader(ROOT / "configs/providers", ROOT / "configs/targets")
    with pytest.raises(ValueError, match="unregistered configuration"):
        loader.load_target("not_registered")


@pytest.mark.parametrize(
    ("provider", "model", "message"),
    [("unknown", "model", "unregistered configuration"), ("gemini", " ", "empty or missing model")],
)
def test_invalid_target_is_rejected(tmp_path: Path, provider: str, model: str, message: str) -> None:
    providers = tmp_path / "providers"
    targets = tmp_path / "targets"
    providers.mkdir()
    targets.mkdir()
    (providers / "gemini.toml").write_text(
        'provider_id="gemini"\nadapter_id="gemini"\napi_key_env="GEMINI_API_KEY"\n', encoding="utf-8"
    )
    (targets / "test.toml").write_text(
        f'target_id="test"\nprovider_id="{provider}"\nadapter_id="gemini"\nmodel="{model}"\nnetwork_permission_env="GATE"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=message):
        TargetLoader(providers, targets).load_target("test")


def test_prepare_uses_target_model_not_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "must-not-be-used")
    request, metadata = ExperimentRunner(ROOT).prepare(
        "EXP-ABE-URL", "baseline", "gemini_3_1_flash_lite"
    )
    assert request.provider_id == "gemini"
    assert request.requested_model == "gemini-3.1-flash-lite"
    assert metadata["target"].target_id == "gemini_3_1_flash_lite"


def test_target_omission_warns_and_uses_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["experiment-run", "EXP-ABE-URL", "--profile", "baseline"]) == 0
    captured = capsys.readouterr()
    assert "deprecated" in captured.err
    assert '"requested_model": "gemini-3.1-flash-lite"' in captured.out


def test_raw_model_option_does_not_exist() -> None:
    with pytest.raises(SystemExit):
        parser().parse_args(
            ["experiment-run", "EXP-ABE-URL", "--profile", "baseline", "--model", "arbitrary"]
        )

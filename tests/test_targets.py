from __future__ import annotations

import hashlib
import base64
from pathlib import Path

import pytest

from agent_risk_lab.cli import dump, live_record, main, parser
from agent_risk_lab.core.experiments import Experiment, ExperimentInput, ExperimentRegistry
from agent_risk_lab.core.models import CommonInteractionResult
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


def test_runner_builds_ordered_text_and_inline_pdf_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = b"Summarize this PDF.\n"
    pdf = b"%PDF-1.4\nsynthetic test PDF\n%%EOF\n"
    experiment = Experiment(
        id="EXP-MULTI",
        type="prompt",
        description="multiple",
        enabled=True,
        inputs=(
            ExperimentInput("text", "EXP-MULTI/prompt.txt", hashlib.sha256(text).hexdigest()),
            ExperimentInput("document", "EXP-MULTI/document.pdf", hashlib.sha256(pdf).hexdigest()),
        ),
    )
    monkeypatch.setattr(ExperimentRegistry, "get", lambda self, eid, verify=False: experiment)
    monkeypatch.setattr(
        ExperimentRegistry,
        "read_inputs",
        lambda self, exp: (
            (exp.inputs[0], text, "text/plain"),
            (exp.inputs[1], pdf, "application/pdf"),
        ),
    )
    request, _ = ExperimentRunner(ROOT).prepare("EXP-MULTI", "baseline")
    assert request.input == [
        {"type": "text", "text": "Summarize this PDF.\n"},
        {
            "type": "document",
            "mime_type": "application/pdf",
            "data": base64.b64encode(pdf).decode("ascii"),
        },
    ]
    serialized = dump(request, ROOT)
    assert "input" not in serialized
    assert "system_instruction" not in serialized
    assert base64.b64encode(pdf).decode("ascii") not in str(serialized)

    calls = []

    class Adapter:
        def create_once(self, common_request):
            calls.append(common_request)
            return CommonInteractionResult(
                provider_id=common_request.provider_id,
                requested_model=common_request.requested_model,
                returned_model=common_request.requested_model,
            )

    monkeypatch.setenv("GEMINI_ALLOW_NETWORK", "1")
    run = ExperimentRunner(ROOT).run(
        "EXP-MULTI", "baseline", live=True, adapter_factory=lambda: Adapter()
    )
    assert len(calls) == 1
    record = live_record(ROOT, run)
    assert record["registered_prompt_sha256"] is None
    assert record["registered_inputs"] == [
        {"type": item.type, "file": item.file, "sha256": item.sha256}
        for item in experiment.inputs
    ]
    assert base64.b64encode(pdf).decode("ascii") not in str(record)

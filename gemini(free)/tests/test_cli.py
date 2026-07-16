import json

import pytest

from gemini_injection_lab.cli import main


def test_dry_run_outputs_safe_preview_without_network(capsys):
    assert main(["dry-run", "B-01", "--profile", "baseline"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["case_id"] == "B-01"
    assert output["execution_mode"] == "dry_run"
    assert "response_text" not in output


def test_unknown_case_fails_without_network():
    try:
        main(["dry-run", "UNKNOWN"])
    except SystemExit as error:
        assert error.code == 2


def test_fs_shadow_dry_run_does_not_create_client(capsys, monkeypatch):
    from gemini_injection_lab.client import GeminiInteractionsClient

    monkeypatch.setattr(GeminiInteractionsClient, "from_environment", lambda: (_ for _ in ()).throw(AssertionError("client created")))
    assert main(["fs-shadow-run", "FS-01", "--profile", "baseline"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["execution_mode"] == "dry_run"
    assert output["api_communication_performed"] is False
    assert output["actual_file_mutation_performed"] is False


def test_fs_shadow_live_requires_environment_gate(monkeypatch):
    monkeypatch.delenv("GEMINI_ALLOW_NETWORK", raising=False)
    with pytest.raises(SystemExit) as error:
        main(["fs-shadow-run", "FS-01", "--live"])
    assert error.value.code == 2


def test_fs_shadow_show_request_and_live_are_incompatible():
    with pytest.raises(SystemExit) as error:
        main(["fs-shadow-run", "FS-01", "--show-request", "--live"])
    assert error.value.code == 2


def test_fs_shadow_only_accepts_registered_id():
    with pytest.raises(SystemExit) as error:
        main(["fs-shadow-run", "../FS-01"])
    assert error.value.code == 2


def test_show_request_masks_synthetic_credentials(capsys):
    assert main(["fs-shadow-run", "FS-01", "--show-request"]) == 0
    output = capsys.readouterr().out
    assert "CANARY_SYNTHETIC_FS01_NOT_REAL" not in output
    assert "[MASKED SYNTHETIC CREDENTIALS]" in output

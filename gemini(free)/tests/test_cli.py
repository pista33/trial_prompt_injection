import json

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

import json

import pytest

from gemini_injection_lab.recorder import JsonlRecorder, _reject_forbidden_keys


def test_rejects_secret_and_state_fields():
    with pytest.raises(ValueError):
        _reject_forbidden_keys({"api_key": "value"})
    with pytest.raises(ValueError):
        _reject_forbidden_keys({"previous_interaction_id": "id"})


def test_recorder_exclusively_creates_file(tmp_path, project_root):
    from gemini_injection_lab.config import Settings
    from gemini_injection_lab.experiment import ExperimentRunner, new_experiment_id

    record = ExperimentRunner(Settings(project_root=project_root)).run_case(
        "B-01", "baseline", 1, new_experiment_id()
    )
    path = tmp_path / "raw.jsonl"
    with JsonlRecorder(path) as recorder:
        recorder.append(record)
    assert json.loads(path.read_text())["case"]["id"] == "B-01"
    with pytest.raises(FileExistsError):
        JsonlRecorder(path)

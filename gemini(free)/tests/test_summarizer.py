import json

from gemini_injection_lab.config import Settings
from gemini_injection_lab.experiment import ExperimentRunner, new_experiment_id
from gemini_injection_lab.summarizer import summarize_records, write_summary_exclusive


def test_summary_is_aggregate_only(project_root, tmp_path):
    record = ExperimentRunner(Settings(project_root=project_root)).run_case(
        "PI-04", "hardened", 1, new_experiment_id()
    )
    summary = summarize_records([record])
    serialized = json.dumps(summary, ensure_ascii=False)
    forbidden = [
        "CANARY_",
        "model_outputs",
        "function_calls",
        "arguments",
        "run_id",
        "interaction_id",
        "response_text",
    ]
    assert not any(item in serialized for item in forbidden)
    output = tmp_path / "summary.json"
    write_summary_exclusive(summary, output)
    assert json.loads(output.read_text())["record_count"] == 1

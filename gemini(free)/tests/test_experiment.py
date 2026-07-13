from types import SimpleNamespace

from gemini_injection_lab.client import GeminiInteractionsClient
from gemini_injection_lab.config import Settings
from gemini_injection_lab.experiment import ExperimentRunner, new_experiment_id


class CountingInteractions:
    def __init__(self):
        self.count = 0

    def create(self, **kwargs):
        self.count += 1
        return SimpleNamespace(
            status="completed",
            model="returned-model",
            usage={"total_tokens": 7},
            steps=[
                SimpleNamespace(
                    id="out",
                    type="model_output",
                    status="done",
                    content=[
                        SimpleNamespace(
                            text="要約: これは文書内容を説明する十分な長さの要約です。\n分類: 研究資料"
                        )
                    ],
                )
            ],
        )


def test_dry_run_never_uses_client(project_root):
    runner = ExperimentRunner(Settings(project_root=project_root))
    record = runner.run_case("B-01", "baseline", 1, new_experiment_id())
    assert record.execution_mode == "dry_run"
    assert record.interaction.status == "dry_run"


def test_mock_trial_calls_provider_once_and_evaluates_task(project_root):
    interactions = CountingInteractions()
    sdk = SimpleNamespace(interactions=interactions)
    settings = Settings(project_root=project_root, requested_model="requested-model")
    record = ExperimentRunner(settings).run_case(
        "B-01",
        "hardened",
        1,
        new_experiment_id(),
        mode="mock",
        client=GeminiInteractionsClient(sdk),
    )
    assert interactions.count == 1
    assert record.evaluation.task_success
    assert not record.evaluation.false_positive
    assert record.model.requested_name == "requested-model"
    assert record.model.returned_name == "returned-model"

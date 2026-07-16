from pathlib import Path
import tomllib
ROOT=Path(__file__).parents[1]
def test_registered_experiment_registry():
    experiments = tomllib.loads(
        (ROOT / "data/experiments/registry.toml").read_text(encoding="utf-8")
    )["experiments"]
    assert [experiment["id"] for experiment in experiments] == ["EXP-ABE-URL"]
    assert all(experiment["enabled"] for experiment in experiments)
    assert all("prompt_sha256" in experiment for experiment in experiments)
    assert all("approved" not in experiment for experiment in experiments)
def test_samples_absent():
    for name in ("model_name_test.txt","cases.json","scenarios.json"): assert not any(ROOT.rglob(name))

from gemini_injection_lab.sandbox import load_cases


def test_exact_initial_case_set(project_root):
    cases = load_cases(project_root / "data" / "cases.json")
    assert sorted(cases) == ["B-01", "B-02", "PI-01", "PI-02", "PI-03", "PI-04"]
    assert cases["B-01"].kind == "benign"
    assert cases["PI-04"].kind == "attack"

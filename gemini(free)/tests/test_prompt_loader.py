from gemini_injection_lab.prompt_loader import PromptLoader, sha256_text


def test_user_task_is_identical_between_profiles(project_root):
    loader = PromptLoader(project_root / "prompts")
    baseline = loader.render("baseline", "同じ文書", "CANARY_A")
    hardened = loader.render("hardened", "同じ文書", "CANARY_A")
    assert baseline.user_input == hardened.user_input
    assert baseline.user_task_sha256 == hardened.user_task_sha256
    assert baseline.system_instruction != hardened.system_instruction


def test_hashes_cover_exact_rendered_text(project_root):
    rendered = PromptLoader(project_root / "prompts").render(
        "baseline", "文書本文", "CANARY_TEST"
    )
    assert rendered.system_sha256 == sha256_text(rendered.system_instruction)
    assert rendered.user_task_sha256 == sha256_text(rendered.user_input)
    assert "プロンプトインジェクションを検出" not in rendered.user_input
    assert "研究資料" in rendered.user_input
    assert "事務資料" in rendered.user_input
    assert "その他" in rendered.user_input

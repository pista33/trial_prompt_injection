import pytest

import gemini_injection_lab.config as config_module
from gemini_injection_lab.config import Settings


def test_settings_never_contains_api_key(project_root):
    settings = Settings(project_root=project_root)
    dumped = settings.model_dump(mode="json")
    assert "api_key" not in dumped
    assert "GEMINI_API_KEY" not in repr(settings)


def test_paths_remain_under_project(project_root):
    settings = Settings(project_root=project_root)
    assert settings.sandbox_root.is_relative_to(project_root)
    assert settings.logs_dir.is_relative_to(project_root)
    assert settings.summaries_dir.is_relative_to(project_root)


def test_settings_uses_current_directory_as_project_root(
    monkeypatch, project_root
):
    monkeypatch.delenv("GEMINI_LAB_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(project_root)

    assert Settings.load().project_root == project_root


def test_explicit_project_root_takes_priority(monkeypatch, project_root, tmp_path):
    monkeypatch.setenv("GEMINI_LAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    assert Settings.load(project_root=project_root).project_root == project_root


def test_environment_project_root_is_used(monkeypatch, project_root, tmp_path):
    monkeypatch.setenv("GEMINI_LAB_PROJECT_ROOT", str(project_root))
    monkeypatch.chdir(tmp_path)

    assert Settings.load().project_root == project_root


def test_missing_required_project_files_raise_clear_error(tmp_path):
    with pytest.raises(ValueError, match=r"invalid project root .*missing required paths"):
        Settings.load(project_root=tmp_path)


def test_installed_package_path_is_not_used_as_project_root(
    monkeypatch, project_root
):
    installed_path = project_root / ".venv" / "lib" / "python3.12"
    monkeypatch.setattr(
        config_module,
        "__file__",
        str(installed_path / "site-packages" / "gemini_injection_lab" / "config.py"),
    )
    monkeypatch.delenv("GEMINI_LAB_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(project_root)

    settings = Settings.load()

    assert settings.project_root == project_root
    assert settings.project_root != installed_path

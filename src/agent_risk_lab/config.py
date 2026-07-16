from pathlib import Path
def project_root()->Path:
    current=Path.cwd()
    if (current/"pyproject.toml").is_file() and (current/"configs").is_dir(): return current
    return Path(__file__).resolve().parents[2]

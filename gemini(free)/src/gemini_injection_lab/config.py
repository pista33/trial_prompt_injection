"""Local configuration without retaining or exposing the API key."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


_REQUIRED_PROJECT_PATHS = (
    ("pyproject.toml", "file"),
    ("data/cases.json", "file"),
    ("data/sandbox/documents", "directory"),
    ("prompts/system_baseline.txt", "file"),
    ("prompts/system_hardened.txt", "file"),
    ("prompts/user_task.txt", "file"),
)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    project_root: Path
    requested_model: str = "UNSET"
    allow_network: bool = False
    max_document_bytes: int = Field(default=64 * 1024, ge=1)
    timeout_seconds: float = Field(default=60.0, gt=0)

    @field_validator("project_root")
    @classmethod
    def validate_project_root(cls, value: Path) -> Path:
        root = value.expanduser().resolve()
        missing = [
            relative
            for relative, kind in _REQUIRED_PROJECT_PATHS
            if not (
                (root / relative).is_file()
                if kind == "file"
                else (root / relative).is_dir()
            )
        ]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(
                f"invalid project root {root}: missing required paths: {joined}"
            )
        return root

    @property
    def prompts_dir(self) -> Path:
        return self.project_root / "prompts"

    @property
    def cases_path(self) -> Path:
        return self.project_root / "data" / "cases.json"

    @property
    def sandbox_root(self) -> Path:
        return self.project_root / "data" / "sandbox" / "documents"

    @property
    def custom_inputs_root(self) -> Path:
        return self.project_root / "data" / "custom_inputs"

    @property
    def logs_dir(self) -> Path:
        return self.project_root / "artifacts" / "logs"

    @property
    def summaries_dir(self) -> Path:
        return self.project_root / "artifacts" / "summaries"

    @classmethod
    def load(cls, project_root: Path | None = None) -> "Settings":
        environment_root = os.getenv("GEMINI_LAB_PROJECT_ROOT")
        if project_root is not None:
            root = Path(project_root)
        elif environment_root and environment_root.strip():
            root = Path(environment_root)
        else:
            root = Path.cwd()
        root = root.expanduser().resolve()
        load_dotenv(root / ".env", override=False)
        return cls(
            project_root=root,
            requested_model=os.getenv("GEMINI_MODEL", "UNSET").strip() or "UNSET",
            allow_network=_as_bool(os.getenv("GEMINI_ALLOW_NETWORK")),
            max_document_bytes=int(os.getenv("MAX_DOCUMENT_BYTES", str(64 * 1024))),
            timeout_seconds=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "60")),
        )

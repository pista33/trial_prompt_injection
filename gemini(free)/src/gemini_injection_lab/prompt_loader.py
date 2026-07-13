"""Read prompt templates and calculate hashes of exact rendered bytes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


PromptProfile = Literal["baseline", "hardened"]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class RenderedPrompts:
    system_instruction: str
    user_input: str
    system_sha256: str
    user_task_sha256: str


class PromptLoader:
    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir.resolve()

    def render(
        self, profile: PromptProfile, document: str, canary: str
    ) -> RenderedPrompts:
        if profile not in {"baseline", "hardened"}:
            raise ValueError(f"unsupported prompt profile: {profile}")
        system_template = self._read(f"system_{profile}.txt")
        user_template = self._read("user_task.txt")
        if system_template.count("{{CANARY}}") != 1:
            raise ValueError("system prompt must contain exactly one Canary placeholder")
        if user_template.count("{{DOCUMENT}}") != 1:
            raise ValueError("user task must contain exactly one document placeholder")
        system_instruction = system_template.replace("{{CANARY}}", canary)
        user_input = user_template.replace("{{DOCUMENT}}", document)
        return RenderedPrompts(
            system_instruction=system_instruction,
            user_input=user_input,
            system_sha256=sha256_text(system_instruction),
            user_task_sha256=sha256_text(user_input),
        )

    def _read(self, filename: str) -> str:
        path = self._prompts_dir / filename
        if path.parent != self._prompts_dir or path.is_symlink():
            raise ValueError(f"unsafe prompt path: {filename}")
        return path.read_text(encoding="utf-8")

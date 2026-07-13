"""Strict, read-only access to registered experiment documents."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path, PurePath

from pydantic import TypeAdapter

from .models import CaseDefinition


class SandboxViolation(ValueError):
    pass


def load_cases(cases_path: Path) -> dict[str, CaseDefinition]:
    raw = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = TypeAdapter(list[CaseDefinition]).validate_python(raw)
    indexed = {case.id: case for case in cases}
    if len(indexed) != len(cases):
        raise ValueError("case IDs must be unique")
    return indexed


class SecureDocumentStore:
    def __init__(self, root: Path, max_bytes: int = 64 * 1024) -> None:
        if root.is_symlink():
            raise SandboxViolation("sandbox root must not be a symbolic link")
        self._root = root.resolve(strict=True)
        self._max_bytes = max_bytes
        if not self._root.is_dir():
            raise SandboxViolation("sandbox root must be a real directory")

    def read_registered(self, filename: str) -> tuple[str, bytes]:
        self._validate_filename(filename)
        candidate = self._root / filename
        if candidate.is_symlink():
            raise SandboxViolation("symbolic links are forbidden")
        resolved = candidate.resolve(strict=True)
        if resolved.parent != self._root:
            raise SandboxViolation("document is outside the sandbox")
        mode = resolved.stat(follow_symlinks=False).st_mode
        if not stat.S_ISREG(mode):
            raise SandboxViolation("document must be a regular file")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(resolved, flags)
        try:
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                data = handle.read(self._max_bytes + 1)
        finally:
            os.close(descriptor)
        if len(data) > self._max_bytes:
            raise SandboxViolation("document exceeds maximum size")
        try:
            return data.decode("utf-8"), data
        except UnicodeDecodeError as error:
            raise SandboxViolation("document must be UTF-8") from error

    @staticmethod
    def _validate_filename(filename: str) -> None:
        if not filename or "\x00" in filename or "/" in filename or "\\" in filename:
            raise SandboxViolation("empty or NUL-containing path")
        path = PurePath(filename)
        if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
            raise SandboxViolation("only a single registered filename is allowed")

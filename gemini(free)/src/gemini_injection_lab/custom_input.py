"""Secure loading and format handling for user-created custom inputs."""

from __future__ import annotations

import base64
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePath


TEXT_LIMIT = 1024 * 1024
PDF_LIMIT = 10 * 1024 * 1024
PDF_MIME = "application/pdf"
PDF_INSTRUCTION_NAME = "pdf_as_prompt_instruction.txt"


class CustomInputError(ValueError):
    pass


@dataclass(frozen=True)
class CustomInput:
    filename: str
    kind: str
    mime_type: str
    raw: bytes
    sha256: str
    text: str | None = None

    @property
    def size(self) -> int:
        return len(self.raw)


def _format_details(suffix: str) -> tuple[str, str, int]:
    """The single registry for supported file formats and their limits."""
    formats = {
        ".txt": ("text", "text/plain", TEXT_LIMIT),
        ".md": ("text", "text/markdown", TEXT_LIMIT),
        ".pdf": ("pdf", PDF_MIME, PDF_LIMIT),
    }
    try:
        return formats[suffix.lower()]
    except KeyError as error:
        raise CustomInputError(f"unsupported input format: {suffix or '<none>'}") from error


class CustomInputStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def read(self, relative_name: str) -> CustomInput:
        if not relative_name or "\x00" in relative_name:
            raise CustomInputError("input path must be a non-empty relative path")
        path = PurePath(relative_name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise CustomInputError("input path must remain inside data/custom_inputs")
        if any(part in {"", "."} for part in path.parts):
            raise CustomInputError("invalid input path component")
        kind, mime_type, limit = _format_details(Path(path.name).suffix)
        raw = self._read_regular_file(path.parts, limit)
        if kind == "pdf" and not raw.startswith(b"%PDF-"):
            raise CustomInputError("invalid PDF header")
        text = None
        if kind == "text":
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise CustomInputError("text input must be UTF-8") from error
        return CustomInput(
            filename=str(path), kind=kind, mime_type=mime_type, raw=raw,
            sha256=hashlib.sha256(raw).hexdigest(), text=text,
        )

    def _read_regular_file(self, parts: tuple[str, ...], limit: int) -> bytes:
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | nofollow)
        try:
            for component in parts[:-1]:
                child = os.open(
                    component, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=directory
                )
                os.close(directory)
                directory = child
            entry = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(entry.st_mode):
                raise CustomInputError("input must be a regular non-symlink file")
            descriptor = os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=directory)
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode):
                    raise CustomInputError("input must be a regular file")
                if info.st_size > limit:
                    raise CustomInputError(f"input exceeds {limit} byte limit")
                raw = b""
                while len(raw) <= limit:
                    chunk = os.read(descriptor, min(65536, limit + 1 - len(raw)))
                    if not chunk:
                        break
                    raw += chunk
                if len(raw) > limit:
                    raise CustomInputError(f"input exceeds {limit} byte limit")
                return raw
            finally:
                os.close(descriptor)
        except OSError as error:
            raise CustomInputError("input path is missing, unsafe, or not a regular file") from error
        finally:
            os.close(directory)


def build_api_input(item: CustomInput, pdf_instruction: str) -> str | list[dict[str, str]]:
    if item.kind == "text":
        assert item.text is not None
        return item.text
    return [
        {"type": "document", "data": base64.b64encode(item.raw).decode("ascii"),
         "mime_type": item.mime_type},
        {"type": "text", "text": pdf_instruction},
    ]

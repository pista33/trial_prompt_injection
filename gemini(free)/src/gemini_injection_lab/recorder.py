"""Exclusive raw JSONL recording with secret-field guards."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import FileRunRecord, RunRecord
from .fs_shadow import FsShadowRunRecord


FORBIDDEN_KEYS = {
    "api_key",
    "apikey",
    "gemini_api_key",
    "authorization",
    "previous_interaction_id",
    "function_result",
}


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"forbidden log field: {key}")
            _reject_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_keys(item)


def new_artifact_path(directory: Path, prefix: str, suffix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"{prefix}_{timestamp}_{uuid4().hex}{suffix}"


class JsonlRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        self._handle = os.fdopen(descriptor, "w", encoding="utf-8")

    def append(self, record: RunRecord | FileRunRecord | FsShadowRunRecord) -> None:
        payload = record.model_dump(mode="json")
        _reject_forbidden_keys(payload)
        self._handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()

    def __enter__(self) -> "JsonlRecorder":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

"""JSON-only Function Declarations; no executable tool implementation exists."""

from __future__ import annotations

import hashlib
import json
from typing import Any


TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "read_file",
        "description": "Requests reading a sandbox-relative file. The experiment only records this request and never executes it.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "send_email",
        "description": "Requests an email. The experiment only records this request and never sends it.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
            "additionalProperties": False,
        },
    },
]


def tool_declarations() -> list[dict[str, Any]]:
    """Return an isolated JSON round-trip copy to prevent accidental mutation."""
    return json.loads(canonical_tool_json())


def canonical_tool_json() -> str:
    return json.dumps(
        TOOL_DECLARATIONS, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def tool_schema_sha256() -> str:
    return hashlib.sha256(canonical_tool_json().encode("utf-8")).hexdigest()


def known_tool_names() -> set[str]:
    return {str(item["name"]) for item in TOOL_DECLARATIONS}

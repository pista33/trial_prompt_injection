from __future__ import annotations

from typing import Any

from .hashing import canonical_hash


def file_copy_declaration(source: str, destination: str) -> dict[str, Any]:
    """Return the sole executable tool, constrained to one registered path pair."""
    return {
        "type": "function",
        "name": "file_copy",
        "description": (
            "Copy the registered source file to the registered destination inside "
            "the isolated shadow workspace. Existing destinations are never overwritten."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": [source]},
                "destination": {"type": "string", "enum": [destination]},
            },
            "required": ["source", "destination"],
        },
    }


def tool_schema_sha256(declarations: list[dict[str, Any]]) -> str:
    return canonical_hash(declarations)

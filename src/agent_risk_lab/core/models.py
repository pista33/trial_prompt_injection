from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class CommonInteractionRequest:
    provider_id: str; requested_model: str; experiment_id: str; experiment_type: str
    profile_id: str; profile_version: int; profile_sha256: str; rendered_system_sha256: str
    system_instruction: str; input: Any; tools: list[dict[str, Any]]; store: bool = False

@dataclass(frozen=True)
class CommonFunctionCall:
    sequence: int; name: str; arguments: dict[str, Any]

@dataclass
class CommonInteractionResult:
    provider_id: str; requested_model: str; returned_model: str | None = None
    status: str | None = None; response_text: str = ""
    function_calls: list[CommonFunctionCall] = field(default_factory=list)
    model_outputs: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict); latency_ms: float | None = None
    api_error: dict[str, Any] = field(default_factory=dict)

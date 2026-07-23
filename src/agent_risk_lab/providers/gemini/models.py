"""Provider-independent data models used by the experiment."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FunctionCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str | None = None
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    known_tool: bool = False
    sequence: int | None = None


class ModelOutputRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str | None = None
    text: str
    status: str | None = None
    sequence: int | None = None


class UnknownStepRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str | None = None
    type: str
    status: str | None = None


class UsageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = None
    output_tokens: int | None = None
    thought_tokens: int | None = None
    total_tokens: int | None = None
    raw_supported_fields: dict[str, int | float | str | bool | None] = Field(
        default_factory=dict
    )


class ApiErrorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred: bool = False
    http_status: int | None = None
    provider_code: str | None = None
    category: str | None = None
    retryable: bool = False
    message_redacted: str | None = None


class InteractionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    model_outputs: list[ModelOutputRecord] = Field(default_factory=list)
    function_calls: list[FunctionCallRecord] = Field(default_factory=list)
    unknown_steps: list[UnknownStepRecord] = Field(default_factory=list)

    @property
    def response_text(self) -> str:
        return "\n".join(output.text for output in self.model_outputs if output.text)


class ClientResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction: InteractionRecord = Field(default_factory=InteractionRecord)
    usage: UsageRecord = Field(default_factory=UsageRecord)
    returned_model_name: str | None = None
    latency_ms: float | None = None
    api_error: ApiErrorRecord = Field(default_factory=ApiErrorRecord)
    retry_count: int = 0

"""Provider-independent data models used by the experiment."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CaseDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["benign", "attack"]
    document: str
    expected_classification: Literal["研究資料", "事務資料", "その他"]
    attack_compliance_markers: list[str] = Field(default_factory=list)


class FunctionCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str | None = None
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    known_tool: bool = False


class ModelOutputRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str | None = None
    text: str
    status: str | None = None


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


class EvaluationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_success: bool = False
    summary_present: bool = False
    classification_present: bool = False
    injection_detected: bool = False
    safe_refusal: bool = False
    false_positive: bool = False
    manual_review_required: bool = False
    canary_in_response_text: bool = False
    canary_in_function_call_arguments: bool = False
    private_canary_read_requested: bool = False
    send_email_requested: bool = False
    canary_send_email_requested: bool = False
    forbidden_function_call: bool = False
    attack_compliance_marker_present: bool = False


class HashRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt_sha256: str
    user_task_sha256: str
    document_sha256: str
    tool_schema_sha256: str
    canary_sha256: str


class RuntimeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    python_version: str
    google_genai_version: str | None = None


class CaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["benign", "attack"]
    prompt_profile: Literal["baseline", "hardened"]


class ModelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_name: str
    returned_name: str | None = None


class TimingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latency_ms: float | None = None


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    experiment_id: str
    run_id: str
    repetition: int = Field(ge=1)
    timestamp_utc: str
    execution_mode: Literal["dry_run", "mock", "live"]
    case: CaseRecord
    runtime: RuntimeRecord
    model: ModelRecord
    hashes: HashRecord
    interaction: InteractionRecord
    usage: UsageRecord
    timing: TimingRecord
    api_error: ApiErrorRecord
    retry_count: int = Field(default=0, ge=0)
    evaluation: EvaluationRecord


class InteractionRequest(BaseModel):
    """Exact provider-independent request passed to the SDK adapter."""

    model_config = ConfigDict(extra="forbid")

    model: str
    system_instruction: str
    input: str
    tools: list[dict[str, Any]]


class FileInteractionRequest(BaseModel):
    """A tool-free, system-instruction-free custom file request."""

    model_config = ConfigDict(extra="forbid")

    model: str
    input: str | list[dict[str, str]]


class FileRunRecord(BaseModel):
    """Raw record for file-run; deliberately contains no input content."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["file_run"] = "file_run"
    timestamp_utc: str
    run_id: str
    execution_mode: Literal["live"] = "live"
    input_filename: str
    input_kind: Literal["text", "pdf"]
    mime_type: str
    input_bytes: int
    input_sha256: str
    pdf_instruction_sha256: str | None = None
    requested_model: str
    returned_model: str | None = None
    google_genai_version: str | None = None
    python_version: str
    interaction_status: str | None = None
    response_text: str = ""
    unexpected_function_names: list[str] = Field(default_factory=list)
    manual_review_required: bool = False
    usage: UsageRecord = Field(default_factory=UsageRecord)
    latency_ms: float | None = None
    api_error: ApiErrorRecord = Field(default_factory=ApiErrorRecord)
    store: Literal[False] = False
    tools_enabled: Literal[False] = False
    system_instruction_enabled: Literal[False] = False

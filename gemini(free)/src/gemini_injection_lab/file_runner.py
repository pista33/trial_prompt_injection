"""Independent orchestration for custom file inputs."""

from __future__ import annotations

import hashlib
import platform
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from .client import google_genai_version
from .custom_input import CustomInput, build_api_input
from .models import FileInteractionRequest, FileRunRecord, ClientResult


class FileOneShotClient(Protocol):
    def create_file_once(self, request: FileInteractionRequest) -> ClientResult: ...


def instruction_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_file_live(
    item: CustomInput, pdf_instruction: str, model: str, client: FileOneShotClient
) -> FileRunRecord:
    if model == "UNSET":
        raise ValueError("an exact model name is required for live mode")
    request = FileInteractionRequest(
        model=model, input=build_api_input(item, pdf_instruction)
    )
    result = client.create_file_once(request)
    function_names = [call.name for call in result.interaction.function_calls]
    return FileRunRecord(
        timestamp_utc=datetime.now(UTC).isoformat(),
        run_id=f"file-run-{uuid4().hex}",
        input_filename=item.filename,
        input_kind=item.kind,
        mime_type=item.mime_type,
        input_bytes=item.size,
        input_sha256=item.sha256,
        pdf_instruction_sha256=(instruction_sha256(pdf_instruction) if item.kind == "pdf" else None),
        requested_model=model,
        returned_model=result.returned_model_name,
        google_genai_version=google_genai_version(),
        python_version=platform.python_version(),
        interaction_status=result.interaction.status,
        response_text=result.interaction.response_text,
        unexpected_function_names=function_names,
        manual_review_required=bool(function_names),
        usage=result.usage,
        latency_ms=result.latency_ms,
        api_error=result.api_error,
    )

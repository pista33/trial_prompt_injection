"""One-request, one-turn experiment orchestration."""

from __future__ import annotations

import platform
import secrets
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import uuid4

from .client import google_genai_version
from .config import Settings
from .evaluator import evaluate
from .models import (
    ApiErrorRecord,
    CaseRecord,
    ClientResult,
    EvaluationRecord,
    HashRecord,
    InteractionRecord,
    InteractionRequest,
    ModelRecord,
    RunRecord,
    RuntimeRecord,
    TimingRecord,
    UsageRecord,
)
from .prompt_loader import PromptLoader, PromptProfile, sha256_bytes, sha256_text
from .sandbox import SecureDocumentStore, load_cases
from .tool_catalog import tool_declarations, tool_schema_sha256


ExecutionMode = Literal["dry_run", "mock", "live"]


class OneShotClient(Protocol):
    def create_once(self, request: InteractionRequest) -> ClientResult: ...


class ExperimentRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cases = load_cases(settings.cases_path)
        self._documents = SecureDocumentStore(
            settings.sandbox_root, max_bytes=settings.max_document_bytes
        )
        self._prompts = PromptLoader(settings.prompts_dir)

    @property
    def case_ids(self) -> list[str]:
        return sorted(self._cases)

    def run_case(
        self,
        case_id: str,
        profile: PromptProfile,
        repetition: int,
        experiment_id: str,
        mode: ExecutionMode = "dry_run",
        client: OneShotClient | None = None,
    ) -> RunRecord:
        if repetition < 1:
            raise ValueError("repetition must be one or greater")
        if case_id not in self._cases:
            raise KeyError(f"unknown case ID: {case_id}")
        case = self._cases[case_id]
        document, document_bytes = self._documents.read_registered(case.document)
        canary = f"CANARY_{secrets.token_hex(16)}"
        prompts = self._prompts.render(profile, document, canary)
        request = InteractionRequest(
            model=self.settings.requested_model,
            system_instruction=prompts.system_instruction,
            input=prompts.user_input,
            tools=tool_declarations(),
        )

        if mode == "dry_run":
            result = ClientResult(
                interaction=InteractionRecord(status="dry_run"),
                usage=UsageRecord(),
                api_error=ApiErrorRecord(),
            )
            evaluation = EvaluationRecord()
        else:
            if client is None:
                raise ValueError("a one-shot client is required outside dry-run")
            if request.model == "UNSET":
                raise ValueError("an exact model name is required for live or mock mode")
            result = client.create_once(request)
            evaluation = evaluate(
                case,
                result.interaction.response_text,
                result.interaction.function_calls,
                canary,
            )

        return RunRecord(
            experiment_id=experiment_id,
            run_id=f"run-{uuid4().hex}",
            repetition=repetition,
            timestamp_utc=datetime.now(UTC).isoformat(),
            execution_mode=mode,
            case=CaseRecord(id=case.id, kind=case.kind, prompt_profile=profile),
            runtime=RuntimeRecord(
                python_version=platform.python_version(),
                google_genai_version=google_genai_version(),
            ),
            model=ModelRecord(
                requested_name=request.model,
                returned_name=result.returned_model_name,
            ),
            hashes=HashRecord(
                system_prompt_sha256=prompts.system_sha256,
                user_task_sha256=prompts.user_task_sha256,
                document_sha256=sha256_bytes(document_bytes),
                tool_schema_sha256=tool_schema_sha256(),
                canary_sha256=sha256_text(canary),
            ),
            interaction=result.interaction,
            usage=result.usage,
            timing=TimingRecord(latency_ms=result.latency_ms),
            api_error=result.api_error,
            retry_count=result.retry_count,
            evaluation=evaluation,
        )


def new_experiment_id() -> str:
    return f"exp-{uuid4().hex}"

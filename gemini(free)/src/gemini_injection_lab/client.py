"""All google-genai and Interactions API specifics are isolated here."""

from __future__ import annotations

import importlib.metadata
import os
import time
from typing import Any

from .models import (
    ApiErrorRecord,
    ClientResult,
    FunctionCallRecord,
    InteractionRecord,
    InteractionRequest,
    ModelOutputRecord,
    UnknownStepRecord,
    UsageRecord,
)
from .tool_catalog import known_tool_names


def google_genai_version() -> str | None:
    try:
        return importlib.metadata.version("google-genai")
    except importlib.metadata.PackageNotFoundError:
        return None


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json", exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    return {}


def _scalar_usage_fields(value: Any) -> dict[str, int | float | str | bool | None]:
    result: dict[str, int | float | str | bool | None] = {}
    for key, item in _as_mapping(value).items():
        if isinstance(item, (int, float, str, bool)) or item is None:
            result[str(key)] = item
    return result


def _first_int(value: Any, names: tuple[str, ...]) -> int | None:
    for name in names:
        item = _get(value, name)
        if isinstance(item, int) and not isinstance(item, bool):
            return item
    return None


def _extract_text(step: Any) -> str:
    texts: list[str] = []
    for content in _get(step, "content", []) or []:
        text = _get(content, "text")
        if isinstance(text, str):
            texts.append(text)
    direct_text = _get(step, "text")
    if isinstance(direct_text, str) and not texts:
        texts.append(direct_text)
    return "".join(texts)


def normalize_interaction(raw: Any) -> ClientResult:
    known = known_tool_names()
    record = InteractionRecord(status=_get(raw, "status"))
    for step in _get(raw, "steps", []) or []:
        step_type = str(_get(step, "type", "unknown"))
        step_id = _get(step, "id")
        status = _get(step, "status")
        if step_type == "function_call":
            name = str(_get(step, "name", ""))
            arguments = _get(step, "arguments", {})
            if not isinstance(arguments, dict):
                arguments = {"_unparsed": str(arguments)}
            record.function_calls.append(
                FunctionCallRecord(
                    step_id=step_id,
                    name=name,
                    arguments=arguments,
                    status=status,
                    known_tool=name in known,
                )
            )
        elif step_type == "model_output":
            record.model_outputs.append(
                ModelOutputRecord(
                    step_id=step_id, text=_extract_text(step), status=status
                )
            )
        else:
            record.unknown_steps.append(
                UnknownStepRecord(step_id=step_id, type=step_type, status=status)
            )

    raw_usage = _get(raw, "usage")
    usage = UsageRecord(
        input_tokens=_first_int(raw_usage, ("input_tokens", "input_token_count")),
        output_tokens=_first_int(raw_usage, ("output_tokens", "output_token_count")),
        thought_tokens=_first_int(
            raw_usage, ("thought_tokens", "thought_token_count")
        ),
        total_tokens=_first_int(raw_usage, ("total_tokens", "total_token_count")),
        raw_supported_fields=_scalar_usage_fields(raw_usage),
    )
    returned_model = _get(raw, "model") or _get(raw, "model_name")
    return ClientResult(
        interaction=record,
        usage=usage,
        returned_model_name=str(returned_model) if returned_model else None,
    )


def _classify_error(error: Exception) -> ApiErrorRecord:
    status = getattr(error, "status_code", None)
    code = getattr(error, "code", None)
    status_int = status if isinstance(status, int) else None
    retryable = status_int in {429, 500, 502, 503, 504}
    if status_int == 429:
        category = "rate_limit"
    elif status_int in {401, 403}:
        category = "authentication_or_permission"
    elif status_int is not None and status_int >= 500:
        category = "provider_server_error"
    elif isinstance(error, TimeoutError):
        category = "timeout"
        retryable = True
    else:
        category = "client_or_api_error"
    return ApiErrorRecord(
        occurred=True,
        http_status=status_int,
        provider_code=str(code) if code is not None else None,
        category=category,
        retryable=retryable,
        message_redacted=type(error).__name__,
    )


class GeminiInteractionsClient:
    """Single-request client. It contains no function execution or follow-up turn."""

    def __init__(self, sdk_client: Any) -> None:
        self._sdk_client = sdk_client

    @classmethod
    def from_environment(cls) -> "GeminiInteractionsClient":
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("live execution is not configured")
        from google import genai

        return cls(genai.Client(api_key=key))

    def create_once(self, request: InteractionRequest) -> ClientResult:
        started = time.perf_counter()
        try:
            raw = self._sdk_client.interactions.create(
                model=request.model,
                system_instruction=request.system_instruction,
                input=request.input,
                tools=request.tools,
                store=False,
            )
            result = normalize_interaction(raw)
        except Exception as error:  # SDK exceptions vary by released version.
            result = ClientResult(api_error=_classify_error(error))
        result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
        result.retry_count = 0
        return result

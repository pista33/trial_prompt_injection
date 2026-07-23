from types import SimpleNamespace

from agent_risk_lab.providers.gemini.client import _classify_error, normalize_interaction


class UsageMetadata:
    def __init__(self, **fields: object) -> None:
        self.__dict__.update(fields)

    def model_dump(self, **_: object) -> dict[str, object]:
        return dict(self.__dict__)


def test_normalizes_total_usage_fields() -> None:
    raw = SimpleNamespace(
        usage=UsageMetadata(
            total_input_tokens=11,
            total_output_tokens=7,
            total_thought_tokens=3,
            total_tokens=21,
        )
    )

    usage = normalize_interaction(raw).usage

    assert usage.input_tokens == 11
    assert usage.output_tokens == 7
    assert usage.thought_tokens == 3
    assert usage.total_tokens == 21


def test_preserves_zero_thought_tokens() -> None:
    raw = SimpleNamespace(usage=UsageMetadata(total_thought_tokens=0))

    assert normalize_interaction(raw).usage.thought_tokens == 0


def test_missing_usage_metadata_is_safe() -> None:
    usage = normalize_interaction(SimpleNamespace()).usage

    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.thought_tokens is None
    assert usage.total_tokens is None
    assert usage.raw_supported_fields == {}


def test_preserves_unknown_scalar_usage_field() -> None:
    raw = SimpleNamespace(
        usage=UsageMetadata(total_input_tokens=5, future_token_metric=13)
    )

    usage = normalize_interaction(raw).usage

    assert usage.raw_supported_fields["future_token_metric"] == 13


def test_error_records_structured_provider_codes_without_message() -> None:
    error = RuntimeError("provider message")
    error.status_code = 400  # type: ignore[attr-defined]
    error.body = {  # type: ignore[attr-defined]
        "error": {
            "status": "INVALID_ARGUMENT",
            "message": "must not be retained",
            "details": [{"reason": "API_KEY_INVALID"}],
        }
    }

    record = _classify_error(error)

    assert record.provider_code == "INVALID_ARGUMENT:API_KEY_INVALID"
    assert record.message_redacted == "RuntimeError"
    assert "must not be retained" not in record.model_dump_json()


def test_error_rejects_unstructured_provider_text() -> None:
    error = RuntimeError("provider message")
    error.body = {  # type: ignore[attr-defined]
        "error": {
            "status": "invalid argument containing request text",
            "reason": "../../secret",
        }
    }

    assert _classify_error(error).provider_code is None


def test_error_extracts_only_allowlisted_code_from_message() -> None:
    error = RuntimeError("Error code: 400 - API_KEY_INVALID for secret value")

    record = _classify_error(error)

    assert record.provider_code == "API_KEY_INVALID"
    assert "secret value" not in record.model_dump_json()

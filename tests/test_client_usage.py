from types import SimpleNamespace

from gemini_injection_lab.client import normalize_interaction


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

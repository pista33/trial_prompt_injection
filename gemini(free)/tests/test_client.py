from types import SimpleNamespace

from gemini_injection_lab.client import GeminiInteractionsClient, normalize_interaction
from gemini_injection_lab.models import InteractionRequest


class FakeInteractions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeSdkClient:
    def __init__(self, response):
        self.interactions = FakeInteractions(response)


def sample_response():
    return SimpleNamespace(
        status="requires_action",
        model="returned-model",
        usage={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
        steps=[
            SimpleNamespace(
                id="s1",
                type="function_call",
                name="read_file",
                arguments={"path": "private/canary.txt"},
                status="done",
            ),
            SimpleNamespace(
                id="s2",
                type="model_output",
                content=[SimpleNamespace(text="要約: 内容です。\n分類: その他")],
                status="done",
            ),
        ],
    )


def test_create_once_is_exactly_one_stateless_call():
    sdk = FakeSdkClient(sample_response())
    client = GeminiInteractionsClient(sdk)
    request = InteractionRequest(
        model="requested-model",
        system_instruction="system",
        input="input",
        tools=[{"type": "function", "name": "read_file"}],
    )
    result = client.create_once(request)
    assert len(sdk.interactions.calls) == 1
    sent = sdk.interactions.calls[0]
    assert sent["store"] is False
    assert "previous_interaction_id" not in sent
    assert "background" not in sent
    assert "automatic_function_calling" not in sent
    assert "function_result" not in sent
    assert result.returned_model_name == "returned-model"
    assert result.retry_count == 0


def test_normalizes_steps_usage_and_status():
    result = normalize_interaction(sample_response())
    assert result.interaction.status == "requires_action"
    assert result.interaction.function_calls[0].name == "read_file"
    assert result.interaction.response_text.startswith("要約:")
    assert result.usage.total_tokens == 15


def test_api_error_is_redacted():
    class KeyBearingError(Exception):
        status_code = 429
        code = "RESOURCE_EXHAUSTED"

    sdk = FakeSdkClient(None)
    sdk.interactions.create = lambda **kwargs: (_ for _ in ()).throw(
        KeyBearingError("secret-value")
    )
    result = GeminiInteractionsClient(sdk).create_once(
        InteractionRequest(model="m", system_instruction="s", input="i", tools=[])
    )
    assert result.api_error.occurred
    assert result.api_error.category == "rate_limit"
    assert "secret-value" not in (result.api_error.message_redacted or "")

from typing import Protocol
from .models import CommonInteractionRequest, CommonInteractionResult

class ProviderAdapter(Protocol):
    provider_id: str
    def create_once(self, request: CommonInteractionRequest) -> CommonInteractionResult: ...

PROVIDER_IDS = ("gemini",)

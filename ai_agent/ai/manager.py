
from time import perf_counter

from .exceptions import (
    AIConfigurationError,
    AIResponseError,
)
from .registry import ProviderRegistry
from .schemas import AIRequest, AIResponse


class AIManager:
    """Central interface for AI generation."""

    def __init__(
        self,
        registry: ProviderRegistry,
        default_provider: str,
    ):
        self.registry = registry
        self.default_provider = default_provider.strip().lower()

        if not self.default_provider:
            raise AIConfigurationError(
                "Default AI provider cannot be empty."
            )

    async def generate(
        self,
        request: AIRequest,
        provider_name: str | None = None,
    ) -> AIResponse:
        selected = provider_name or self.default_provider
        provider = self.registry.get(selected)

        started = perf_counter()
        response = await provider.generate(request)
        elapsed = perf_counter() - started

        if not response.success:
            raise AIResponseError(
                f"AI provider '{provider.name}' reported failure."
            )

        if not response.text.strip():
            raise AIResponseError(
                f"AI provider '{provider.name}' returned empty text."
            )

        # The manager measures duration if the adapter
        # has not supplied its own measurement.
        if response.duration_seconds is None:
            response = response.model_copy(
                update={"duration_seconds": elapsed}
            )

        return response

    def available_providers(self) -> list[str]:
        return self.registry.list_providers()

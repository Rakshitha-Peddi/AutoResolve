
from .base import AIProvider
from .exceptions import (
    AIConfigurationError,
    AINoProviderError,
)


class ProviderRegistry:
    """Register and retrieve AI providers."""

    def __init__(self):
        self._providers: dict[str, AIProvider] = {}

    def register(self, provider: AIProvider) -> None:
        name = provider.name.strip().lower()

        if not name:
            raise AIConfigurationError(
                "Provider name cannot be empty."
            )

        if name in self._providers:
            raise AIConfigurationError(
                f"Provider '{name}' is already registered."
            )

        self._providers[name] = provider

    def get(self, name: str) -> AIProvider:
        provider = self._providers.get(name.strip().lower())

        if provider is None:
            raise AINoProviderError(
                f"AI provider '{name}' is not registered."
            )

        return provider

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

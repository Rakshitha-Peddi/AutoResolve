
from abc import ABC, abstractmethod

from .schemas import AIRequest, AIResponse


class AIProvider(ABC):
    """Common interface for all AI providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""

    @abstractmethod
    async def generate(self, request: AIRequest) -> AIResponse:
        """Generate an AI response."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check whether the provider is available."""

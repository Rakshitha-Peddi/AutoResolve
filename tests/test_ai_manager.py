
import pytest

from ai_agent.ai.base import AIProvider
from ai_agent.ai.exceptions import (
    AIConfigurationError,
    AINoProviderError,
    AIResponseError,
)
from ai_agent.ai.manager import AIManager
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import (
    AIMessage,
    AIRequest,
    AIResponse,
)


class MockProvider(AIProvider):
    @property
    def name(self) -> str:
        return "mock"

    async def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            text="Mock AI generated a response.",
            provider=self.name,
            model="mock-model",
        )

    async def health_check(self) -> bool:
        return True


class EmptyProvider(MockProvider):
    @property
    def name(self) -> str:
        return "empty"

    async def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            text="",
            provider=self.name,
            model="empty-model",
        )


def make_request() -> AIRequest:
    return AIRequest(
        task="bug_fix",
        messages=[
            AIMessage(
                role="user",
                content="Fix a Python bug.",
            )
        ],
    )


@pytest.mark.asyncio
async def test_manager_generates_response():
    registry = ProviderRegistry()
    registry.register(MockProvider())

    manager = AIManager(registry, "mock")
    response = await manager.generate(make_request())

    assert response.success is True
    assert response.provider == "mock"
    assert response.model == "mock-model"
    assert response.text == "Mock AI generated a response."
    assert response.duration_seconds is not None


def test_registry_lists_providers():
    registry = ProviderRegistry()
    registry.register(MockProvider())

    assert registry.list_providers() == ["mock"]


def test_registry_rejects_duplicate_provider():
    registry = ProviderRegistry()
    registry.register(MockProvider())

    with pytest.raises(AIConfigurationError):
        registry.register(MockProvider())


@pytest.mark.asyncio
async def test_manager_rejects_missing_provider():
    manager = AIManager(ProviderRegistry(), "missing")

    with pytest.raises(AINoProviderError):
        await manager.generate(make_request())


@pytest.mark.asyncio
async def test_manager_rejects_empty_response():
    registry = ProviderRegistry()
    registry.register(EmptyProvider())

    manager = AIManager(registry, "empty")

    with pytest.raises(AIResponseError):
        await manager.generate(make_request())


import pytest

from ai_agent.ai.base import AIProvider
from ai_agent.ai.exceptions import (
    AIAuthenticationError,
    AINoProviderError,
    AIProviderError,
    AIRateLimitError,
)
from ai_agent.ai.manager import AIManager
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import (
    AIMessage,
    AIRequest,
    AIResponse,
)


class FakeProvider(AIProvider):
    def __init__(self, name, error=None):
        self._name = name
        self.error = error
        self.calls = 0

    @property
    def name(self):
        return self._name

    async def health_check(self):
        return True

    async def generate(self, request):
        self.calls += 1

        if self.error:
            raise self.error

        return AIResponse(
            text=f"Response from {self.name}",
            provider=self.name,
            model="mock-model",
        )


def make_request():
    return AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(role="user", content="Find a bug.")
        ],
    )


def make_manager(primary, backup, enabled=True):
    registry = ProviderRegistry()
    registry.register(primary)
    registry.register(backup)

    return AIManager(
        registry=registry,
        default_provider=primary.name,
        fallback_enabled=enabled,
        fallback_providers=(backup.name,),
    )


@pytest.mark.asyncio
async def test_primary_provider_success():
    primary = FakeProvider("gemini")
    backup = FakeProvider("groq")

    manager = make_manager(primary, backup)
    result = await manager.generate(make_request())

    assert result.provider == "gemini"
    assert primary.calls == 1
    assert backup.calls == 0


@pytest.mark.asyncio
async def test_fallback_on_provider_failure():
    primary = FakeProvider(
        "gemini",
        AIProviderError("HTTP 503"),
    )
    backup = FakeProvider("groq")

    manager = make_manager(primary, backup)
    result = await manager.generate(make_request())

    assert result.provider == "groq"
    assert primary.calls == 1
    assert backup.calls == 1


@pytest.mark.asyncio
async def test_fallback_on_rate_limit():
    primary = FakeProvider(
        "gemini",
        AIRateLimitError("HTTP 429"),
    )
    backup = FakeProvider("groq")

    manager = make_manager(primary, backup)
    result = await manager.generate(make_request())

    assert result.provider == "groq"


@pytest.mark.asyncio
async def test_fallback_disabled():
    primary = FakeProvider(
        "gemini",
        AIProviderError("HTTP 503"),
    )
    backup = FakeProvider("groq")

    manager = make_manager(
        primary,
        backup,
        enabled=False,
    )

    with pytest.raises(AIProviderError):
        await manager.generate(make_request())

    assert backup.calls == 0


@pytest.mark.asyncio
async def test_all_providers_fail():
    primary = FakeProvider(
        "gemini",
        AIProviderError("HTTP 503"),
    )
    backup = FakeProvider(
        "groq",
        AIRateLimitError("HTTP 429"),
    )

    manager = make_manager(primary, backup)

    with pytest.raises(AINoProviderError):
        await manager.generate(make_request())

    assert primary.calls == 1
    assert backup.calls == 1


@pytest.mark.asyncio
async def test_authentication_failure_does_not_fallback():
    primary = FakeProvider(
        "gemini",
        AIAuthenticationError("Invalid credentials"),
    )
    backup = FakeProvider("groq")

    manager = make_manager(primary, backup)

    with pytest.raises(AIAuthenticationError):
        await manager.generate(make_request())

    assert backup.calls == 0

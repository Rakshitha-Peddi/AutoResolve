
import asyncio

import pytest
from test_ai_fallback import FakeProvider

from ai_agent.ai.exceptions import (
    AIConfigurationError,
    AITimeoutError,
    AITransientError,
)
from ai_agent.ai.manager import AIManager
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import AIMessage, AIRequest


class RecoveringProvider(FakeProvider):
    async def generate(self, request):
        self.calls += 1

        if self.calls == 1:
            raise AITransientError("Temporary HTTP 503")

        return await self._success()

    async def _success(self):
        from ai_agent.ai.schemas import AIResponse

        return AIResponse(
            text="Recovered successfully",
            provider=self.name,
            model="mock-model",
        )


class SlowProvider(FakeProvider):
    async def generate(self, request):
        self.calls += 1
        await asyncio.sleep(0.1)
        return await super().generate(request)


def make_request():
    return AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(role="user", content="Find a bug.")
        ],
    )


def make_manager(provider, **kwargs):
    registry = ProviderRegistry()
    registry.register(provider)

    return AIManager(
        registry=registry,
        default_provider=provider.name,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_retries_temporary_failure(monkeypatch):
    async def no_delay(seconds):
        return None

    monkeypatch.setattr(
        "ai_agent.ai.manager.asyncio.sleep",
        no_delay,
    )

    provider = RecoveringProvider("gemini")
    manager = make_manager(
        provider,
        max_retries=1,
    )

    result = await manager.generate(make_request())

    assert result.text == "Recovered successfully"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_no_retry_by_default():
    provider = RecoveringProvider("gemini")
    manager = make_manager(provider)

    with pytest.raises(AITransientError):
        await manager.generate(make_request())

    assert provider.calls == 1


@pytest.mark.asyncio
async def test_timeout_is_enforced():
    provider = SlowProvider("gemini")
    manager = make_manager(
        provider,
        request_timeout=0.01,
    )

    with pytest.raises(AITimeoutError):
        await manager.generate(make_request())

    assert provider.calls == 1


def test_invalid_retry_configuration():
    provider = FakeProvider("gemini")

    with pytest.raises(AIConfigurationError):
        make_manager(provider, max_retries=3)


def test_invalid_timeout_configuration():
    provider = FakeProvider("gemini")

    with pytest.raises(AIConfigurationError):
        make_manager(provider, request_timeout=0)

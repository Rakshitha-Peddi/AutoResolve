
"""Safety tests for AI retry and request-budget interaction."""

import pytest
from test_ai_fallback import FakeProvider

from ai_agent.ai.exceptions import AITransientError
from ai_agent.ai.manager import AIManager
from ai_agent.ai.model_router import ModelRouter
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import AIMessage, AIRequest
from ai_agent.ai.usage_tracker import (
    AIUsageLimitError,
    AIUsageTracker,
)


class TransientProvider(FakeProvider):
    """Fake provider that always fails temporarily."""

    async def generate(self, request):
        self.calls += 1
        raise AITransientError("Simulated HTTP 503")


def make_request():
    return AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(role="user", content="Find the bug.")
        ],
    )


def make_manager(
    gemini,
    groq=None,
    *,
    limits,
    max_retries=0,
    fallback_enabled=False,
):
    registry = ProviderRegistry()
    registry.register(gemini)

    enabled = ["gemini"]

    if groq is not None:
        registry.register(groq)
        enabled.append("groq")

    tracker = AIUsageTracker(limits)

    manager = AIManager(
        registry=registry,
        default_provider="gemini",
        model_router=ModelRouter(tuple(enabled)),
        usage_tracker=tracker,
        fallback_enabled=fallback_enabled,
        max_retries=max_retries,
    )

    return manager, tracker


@pytest.mark.asyncio
async def test_each_retry_consumes_a_budget_unit(monkeypatch):
    async def skip_delay(seconds):
        return None

    monkeypatch.setattr(
        "ai_agent.ai.manager.asyncio.sleep",
        skip_delay,
    )

    gemini = TransientProvider("gemini")

    manager, tracker = make_manager(
        gemini,
        limits={"gemini": 3},
        max_retries=2,
    )

    with pytest.raises(AITransientError):
        await manager.generate(make_request())

    assert gemini.calls == 3
    assert tracker.get_usage("gemini")["used"] == 3


@pytest.mark.asyncio
async def test_retry_stops_when_budget_is_exhausted(monkeypatch):
    async def skip_delay(seconds):
        return None

    monkeypatch.setattr(
        "ai_agent.ai.manager.asyncio.sleep",
        skip_delay,
    )

    gemini = TransientProvider("gemini")

    manager, tracker = make_manager(
        gemini,
        limits={"gemini": 2},
        max_retries=2,
    )

    with pytest.raises(AIUsageLimitError):
        await manager.generate(make_request())

    assert gemini.calls == 2
    assert tracker.get_usage("gemini")["used"] == 2


@pytest.mark.asyncio
async def test_budget_exhaustion_during_retry_uses_backup(
    monkeypatch,
):
    async def skip_delay(seconds):
        return None

    monkeypatch.setattr(
        "ai_agent.ai.manager.asyncio.sleep",
        skip_delay,
    )

    gemini = TransientProvider("gemini")
    groq = FakeProvider("groq")

    manager, tracker = make_manager(
        gemini,
        groq,
        limits={"gemini": 1, "groq": 2},
        max_retries=2,
        fallback_enabled=True,
    )

    response = await manager.generate(make_request())

    assert response.provider == "groq"
    assert gemini.calls == 1
    assert groq.calls == 1
    assert tracker.get_usage("gemini")["used"] == 1
    assert tracker.get_usage("groq")["used"] == 1

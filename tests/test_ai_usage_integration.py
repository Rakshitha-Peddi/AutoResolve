
import pytest
from test_ai_fallback import FakeProvider

from ai_agent.ai.exceptions import AINoProviderError
from ai_agent.ai.manager import AIManager
from ai_agent.ai.model_router import ModelRouter
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import AIMessage, AIRequest
from ai_agent.ai.usage_tracker import (
    AIUsageLimitError,
    AIUsageTracker,
)


def make_request():
    return AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(
                role="user",
                content="Find the bug.",
            )
        ],
    )


def make_manager(
    gemini,
    groq=None,
    *,
    limits=None,
    fallback_enabled=False,
):
    registry = ProviderRegistry()
    registry.register(gemini)

    enabled = ["gemini"]

    if groq is not None:
        registry.register(groq)
        enabled.append("groq")

    tracker = AIUsageTracker(
        limits or {"gemini": 2, "groq": 2}
    )

    router = ModelRouter(
        tuple(enabled),
        default_provider="gemini",
    )

    manager = AIManager(
        registry=registry,
        default_provider="gemini",
        model_router=router,
        fallback_enabled=fallback_enabled,
        usage_tracker=tracker,
    )

    return manager, tracker


@pytest.mark.asyncio
async def test_successful_request_is_counted():
    gemini = FakeProvider("gemini")
    manager, tracker = make_manager(gemini)

    response = await manager.generate(make_request())

    assert response.provider == "gemini"
    assert gemini.calls == 1
    assert tracker.get_usage("gemini")["used"] == 1


@pytest.mark.asyncio
async def test_exhausted_budget_blocks_api_call():
    gemini = FakeProvider("gemini")
    manager, tracker = make_manager(
        gemini,
        limits={"gemini": 1},
    )

    await manager.generate(make_request())

    with pytest.raises(AIUsageLimitError):
        await manager.generate(make_request())

    assert gemini.calls == 1
    assert tracker.get_usage("gemini")["used"] == 1


@pytest.mark.asyncio
async def test_exhausted_primary_uses_allowed_backup():
    gemini = FakeProvider("gemini")
    groq = FakeProvider("groq")

    manager, tracker = make_manager(
        gemini,
        groq,
        limits={"gemini": 1, "groq": 2},
        fallback_enabled=True,
    )

    tracker.reserve_request("gemini")

    response = await manager.generate(make_request())

    assert response.provider == "groq"
    assert gemini.calls == 0
    assert groq.calls == 1
    assert tracker.get_usage("groq")["used"] == 1


@pytest.mark.asyncio
async def test_all_budgets_exhausted_stops_safely():
    gemini = FakeProvider("gemini")
    groq = FakeProvider("groq")

    manager, tracker = make_manager(
        gemini,
        groq,
        limits={"gemini": 1, "groq": 1},
        fallback_enabled=True,
    )

    tracker.reserve_request("gemini")
    tracker.reserve_request("groq")

    with pytest.raises(AINoProviderError):
        await manager.generate(make_request())

    assert gemini.calls == 0
    assert groq.calls == 0


@pytest.mark.asyncio
async def test_disabled_fallback_does_not_use_backup():
    gemini = FakeProvider("gemini")
    groq = FakeProvider("groq")

    manager, tracker = make_manager(
        gemini,
        groq,
        limits={"gemini": 1, "groq": 2},
        fallback_enabled=False,
    )

    tracker.reserve_request("gemini")

    with pytest.raises(AIUsageLimitError):
        await manager.generate(make_request())

    assert gemini.calls == 0
    assert groq.calls == 0

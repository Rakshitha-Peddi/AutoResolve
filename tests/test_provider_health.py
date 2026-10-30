
import pytest
from test_ai_fallback import FakeProvider

from ai_agent.ai.exceptions import (
    AINoProviderError,
    AIProviderError,
)
from ai_agent.ai.manager import AIManager
from ai_agent.ai.provider_health import ProviderHealthTracker
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import AIMessage, AIRequest


def test_provider_initially_available():
    tracker = ProviderHealthTracker()

    assert tracker.is_available("gemini")


def test_provider_enters_cooldown():
    tracker = ProviderHealthTracker(
        cooldown_seconds=60,
        clock=lambda: 100,
    )

    tracker.record_failure("gemini")

    assert not tracker.is_available("gemini")
    assert tracker.remaining_cooldown("gemini") == 60


def test_provider_recovers_after_cooldown():
    current_time = [100]

    tracker = ProviderHealthTracker(
        cooldown_seconds=60,
        clock=lambda: current_time[0],
    )

    tracker.record_failure("gemini")
    current_time[0] = 161

    assert tracker.is_available("gemini")


def test_success_resets_failure_state():
    tracker = ProviderHealthTracker(
        clock=lambda: 100,
    )

    tracker.record_failure("groq")
    tracker.record_success("groq")

    assert tracker.is_available("groq")
    assert tracker.remaining_cooldown("groq") == 0


@pytest.mark.asyncio
async def test_manager_skips_cooling_provider():
    primary = FakeProvider(
        "gemini",
        AIProviderError("HTTP 503"),
    )
    backup = FakeProvider("groq")

    registry = ProviderRegistry()
    registry.register(primary)
    registry.register(backup)

    tracker = ProviderHealthTracker(
        cooldown_seconds=60,
        clock=lambda: 100,
    )

    manager = AIManager(
        registry=registry,
        default_provider="gemini",
        fallback_enabled=True,
        fallback_providers=("groq",),
        health_tracker=tracker,
    )

    request = AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(role="user", content="Find a bug.")
        ],
    )

    first = await manager.generate(request)
    second = await manager.generate(request)

    assert first.provider == "groq"
    assert second.provider == "groq"
    assert primary.calls == 1
    assert backup.calls == 2


@pytest.mark.asyncio
async def test_all_cooling_providers_fail_safely():
    registry = ProviderRegistry()
    registry.register(FakeProvider("gemini"))
    registry.register(FakeProvider("groq"))

    tracker = ProviderHealthTracker(
        clock=lambda: 100,
    )
    tracker.record_failure("gemini")
    tracker.record_failure("groq")

    manager = AIManager(
        registry,
        "gemini",
        fallback_enabled=True,
        fallback_providers=("groq",),
        health_tracker=tracker,
    )

    request = AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(role="user", content="Find a bug.")
        ],
    )

    with pytest.raises(AINoProviderError):
        await manager.generate(request)

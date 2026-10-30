
"""Verify persistent budgets work with the AI manager."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from test_ai_fallback import FakeProvider

from ai_agent.ai.exceptions import AINoProviderError
from ai_agent.ai.manager import AIManager
from ai_agent.ai.model_router import ModelRouter
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import AIMessage, AIRequest
from ai_agent.ai.sqlite_usage_tracker import SQLiteUsageTracker
from ai_agent.ai.usage_tracker import AIUsageLimitError


def make_request():
    return AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(role="user", content="Find the bug.")
        ],
    )


def make_manager(database, gemini, groq=None):
    registry = ProviderRegistry()
    registry.register(gemini)

    enabled = ["gemini"]

    if groq is not None:
        registry.register(groq)
        enabled.append("groq")

    tracker = SQLiteUsageTracker(
        database,
        {"gemini": 1, "groq": 2},
    )

    manager = AIManager(
        registry=registry,
        default_provider="gemini",
        model_router=ModelRouter(tuple(enabled)),
        fallback_enabled=groq is not None,
        usage_tracker=tracker,
    )

    return manager, tracker


@pytest.mark.asyncio
async def test_manager_persists_usage_after_restart(tmp_path):
    database = tmp_path / "usage.db"

    gemini = FakeProvider("gemini")
    manager, tracker = make_manager(database, gemini)

    response = await manager.generate(make_request())

    assert response.provider == "gemini"
    assert tracker.get_usage("gemini")["used"] == 1

    # Simulate a restart by constructing a new manager
    # and tracker against the existing database.
    new_gemini = FakeProvider("gemini")
    new_manager, new_tracker = make_manager(
        database,
        new_gemini,
    )

    with pytest.raises(AIUsageLimitError):
        await new_manager.generate(make_request())

    assert new_gemini.calls == 0
    assert new_tracker.get_usage("gemini")["used"] == 1


@pytest.mark.asyncio
async def test_persisted_primary_limit_uses_backup(tmp_path):
    database = tmp_path / "usage.db"

    original_tracker = SQLiteUsageTracker(
        database,
        {"gemini": 1, "groq": 2},
    )
    original_tracker.reserve_request("gemini")

    gemini = FakeProvider("gemini")
    groq = FakeProvider("groq")

    manager, tracker = make_manager(
        database,
        gemini,
        groq,
    )

    response = await manager.generate(make_request())

    assert response.provider == "groq"
    assert gemini.calls == 0
    assert groq.calls == 1
    assert tracker.get_usage("groq")["used"] == 1


@pytest.mark.asyncio
async def test_persisted_limits_stop_all_providers(tmp_path):
    database = tmp_path / "usage.db"

    original_tracker = SQLiteUsageTracker(
        database,
        {"gemini": 1, "groq": 2},
    )
    original_tracker.reserve_request("gemini")
    original_tracker.reserve_request("groq")
    original_tracker.reserve_request("groq")

    gemini = FakeProvider("gemini")
    groq = FakeProvider("groq")

    manager, _ = make_manager(database, gemini, groq)

    with pytest.raises(AINoProviderError):
        await manager.generate(make_request())

    assert gemini.calls == 0
    assert groq.calls == 0


def test_concurrent_reservations_respect_limit(tmp_path):
    database = tmp_path / "usage.db"
    limit = 3

    tracker = SQLiteUsageTracker(
        database,
        {"gemini": limit},
    )

    def try_reserve():
        try:
            tracker.reserve_request("gemini")
            return True
        except AIUsageLimitError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: try_reserve(), range(12)))

    assert sum(results) == limit
    assert tracker.get_usage("gemini")["used"] == limit


from datetime import UTC, datetime

import pytest

from ai_agent.ai.usage_tracker import (
    AIUsageLimitError,
    AIUsageTracker,
)


def test_initial_usage_is_zero():
    tracker = AIUsageTracker({"gemini": 20})

    assert tracker.get_usage("gemini") == {
        "used": 0,
        "limit": 20,
        "remaining": 20,
    }


def test_request_increases_usage():
    tracker = AIUsageTracker({"gemini": 2})

    tracker.reserve_request("gemini")

    assert tracker.get_usage("gemini")["used"] == 1
    assert tracker.get_usage("gemini")["remaining"] == 1


def test_daily_limit_is_enforced():
    tracker = AIUsageTracker({"gemini": 2})

    tracker.reserve_request("gemini")
    tracker.reserve_request("gemini")

    with pytest.raises(AIUsageLimitError):
        tracker.reserve_request("gemini")

    assert tracker.get_usage("gemini")["used"] == 2


def test_providers_have_independent_budgets():
    tracker = AIUsageTracker({
        "gemini": 1,
        "groq": 2,
    })

    tracker.reserve_request("gemini")
    tracker.reserve_request("groq")

    assert tracker.get_usage("gemini")["remaining"] == 0
    assert tracker.get_usage("groq")["remaining"] == 1


def test_usage_resets_on_new_utc_day():
    current_time = [
        datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    ]

    tracker = AIUsageTracker(
        {"gemini": 1},
        clock=lambda: current_time[0],
    )

    tracker.reserve_request("gemini")
    assert tracker.get_usage("gemini")["remaining"] == 0

    current_time[0] = datetime(
        2026, 10, 31, 0, 1, tzinfo=UTC
    )

    assert tracker.get_usage("gemini")["used"] == 0

    tracker.reserve_request("gemini")
    assert tracker.get_usage("gemini")["used"] == 1


def test_unknown_provider_is_rejected():
    tracker = AIUsageTracker({"gemini": 1})

    with pytest.raises(AIUsageLimitError):
        tracker.reserve_request("unapproved-provider")


def test_invalid_limits_are_rejected():
    with pytest.raises(ValueError):
        AIUsageTracker({"gemini": -1})

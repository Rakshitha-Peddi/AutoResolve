
"""Tests for persistent AI request budgets."""

from datetime import UTC, datetime

import pytest

from ai_agent.ai.sqlite_usage_tracker import SQLiteUsageTracker
from ai_agent.ai.usage_tracker import AIUsageLimitError


def test_initial_usage_is_zero(tmp_path):
    tracker = SQLiteUsageTracker(
        tmp_path / "usage.db",
        {"gemini": 2},
    )

    assert tracker.get_usage("gemini") == {
        "used": 0,
        "limit": 2,
        "remaining": 2,
    }


def test_request_is_persisted_after_reopening(tmp_path):
    database = tmp_path / "usage.db"

    first = SQLiteUsageTracker(
        database, {"gemini": 2}
    )
    first.reserve_request("gemini")

    second = SQLiteUsageTracker(
        database, {"gemini": 2}
    )

    assert second.get_usage("gemini")["used"] == 1


def test_limit_survives_restart(tmp_path):
    database = tmp_path / "usage.db"

    first = SQLiteUsageTracker(
        database, {"gemini": 1}
    )
    first.reserve_request("gemini")

    second = SQLiteUsageTracker(
        database, {"gemini": 1}
    )

    with pytest.raises(AIUsageLimitError):
        second.reserve_request("gemini")


def test_providers_are_tracked_separately(tmp_path):
    tracker = SQLiteUsageTracker(
        tmp_path / "usage.db",
        {"gemini": 1, "groq": 2},
    )

    tracker.reserve_request("gemini")
    tracker.reserve_request("groq")

    assert tracker.get_usage("gemini")["used"] == 1
    assert tracker.get_usage("groq")["used"] == 1
    assert tracker.get_usage("groq")["remaining"] == 1


def test_new_utc_day_has_fresh_budget(tmp_path):
    current_time = [
        datetime(2026, 10, 30, 12, tzinfo=UTC)
    ]

    tracker = SQLiteUsageTracker(
        tmp_path / "usage.db",
        {"gemini": 1},
        clock=lambda: current_time[0],
    )

    tracker.reserve_request("gemini")

    current_time[0] = datetime(
        2026, 10, 31, 1, tzinfo=UTC
    )

    assert tracker.get_usage("gemini")["used"] == 0

    tracker.reserve_request("gemini")
    assert tracker.get_usage("gemini")["used"] == 1


def test_unapproved_provider_is_rejected(tmp_path):
    tracker = SQLiteUsageTracker(
        tmp_path / "usage.db",
        {"gemini": 1},
    )

    with pytest.raises(AIUsageLimitError):
        tracker.reserve_request("unknown")


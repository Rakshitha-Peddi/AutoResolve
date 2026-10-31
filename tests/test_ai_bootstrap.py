
"""Tests for AutoResolve AI manager configuration."""

import pytest
from test_ai_fallback import FakeProvider

from ai_agent.ai import bootstrap
from ai_agent.ai.exceptions import AIConfigurationError


@pytest.fixture
def configured_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "AI_USAGE_DB_PATH",
        str(tmp_path / "usage.sqlite3"),
    )
    monkeypatch.setenv(
        "AI_ENABLED_PROVIDERS",
        "gemini,groq",
    )
    monkeypatch.setenv(
        "AI_PRIMARY_PROVIDER",
        "gemini",
    )
    monkeypatch.setenv(
        "AI_FALLBACK_ENABLED",
        "false",
    )
    monkeypatch.setenv(
        "ALLOW_PAID_PROVIDERS",
        "false",
    )
    monkeypatch.setenv(
        "AI_REQUEST_TIMEOUT",
        "60",
    )
    monkeypatch.setenv(
        "AI_MAX_RETRIES",
        "0",
    )
    monkeypatch.setenv(
        "AI_GEMINI_DAILY_LIMIT",
        "2",
    )
    monkeypatch.setenv(
        "AI_GROQ_DAILY_LIMIT",
        "3",
    )

    # Avoid real SDK initialization and external requests.
    monkeypatch.setattr(
        bootstrap,
        "GeminiProvider",
        lambda: FakeProvider("gemini"),
    )
    monkeypatch.setattr(
        bootstrap,
        "GroqProvider",
        lambda: FakeProvider("groq"),
    )


def test_factory_builds_configured_manager(
    configured_environment,
):
    manager = bootstrap.build_ai_manager()

    assert manager.default_provider == "gemini"
    assert not manager.fallback_enabled
    assert set(manager.available_providers()) == {
        "gemini",
        "groq",
    }
    assert manager.usage_tracker.get_usage("gemini") == {
        "used": 0,
        "limit": 2,
        "remaining": 2,
    }


def test_factory_rejects_unknown_provider(
    configured_environment,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI_ENABLED_PROVIDERS",
        "gemini,unapproved",
    )

    with pytest.raises(AIConfigurationError):
        bootstrap.build_ai_manager()


def test_factory_rejects_paid_configuration(
    configured_environment,
    monkeypatch,
):
    monkeypatch.setenv("ALLOW_PAID_PROVIDERS", "true")

    with pytest.raises(AIConfigurationError):
        bootstrap.build_ai_manager()


def test_factory_rejects_negative_budget(
    configured_environment,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI_GEMINI_DAILY_LIMIT", "-1"
    )

    with pytest.raises(AIConfigurationError):
        bootstrap.build_ai_manager()

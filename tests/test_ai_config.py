
import pytest

from ai_agent.ai.config import load_ai_settings
from ai_agent.ai.exceptions import AIConfigurationError


def test_default_configuration(monkeypatch):
    for name in (
        "AI_PRIMARY_PROVIDER",
        "AI_ENABLED_PROVIDERS",
        "AI_FALLBACK_ENABLED",
        "AI_REQUEST_TIMEOUT",
        "ALLOW_PAID_PROVIDERS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_ai_settings()

    assert settings.primary_provider == "gemini"
    assert settings.enabled_providers == ("gemini",)
    assert settings.allow_paid_providers is False


def test_multiple_providers(monkeypatch):
    monkeypatch.setenv(
        "AI_ENABLED_PROVIDERS", "gemini,groq"
    )
    monkeypatch.setenv(
        "AI_PRIMARY_PROVIDER", "gemini"
    )
    monkeypatch.setenv(
        "ALLOW_PAID_PROVIDERS", "false"
    )

    settings = load_ai_settings()

    assert settings.enabled_providers == (
        "gemini", "groq"
    )


def test_paid_providers_rejected(monkeypatch):
    monkeypatch.setenv(
        "ALLOW_PAID_PROVIDERS", "true"
    )

    with pytest.raises(AIConfigurationError):
        load_ai_settings()


"""Tests for outbound AI prompt security."""

import pytest
from test_ai_fallback import FakeProvider

from ai_agent.ai.manager import AIManager
from ai_agent.ai.prompt_safety import (
    AISensitiveContentError,
    validate_outbound_prompt,
)
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import AIMessage, AIRequest


def test_rejects_hardcoded_github_token_assignment():
    with pytest.raises(AISensitiveContentError):
        validate_outbound_prompt(
            'github_token = "example-secret-value"'
        )


def test_rejects_sensitive_json_field():
    with pytest.raises(AISensitiveContentError):
        validate_outbound_prompt(
            '{"password": "example-password"}'
        )


def test_rejects_private_key_material():
    with pytest.raises(AISensitiveContentError):
        validate_outbound_prompt(
            "-----BEGIN PRIVATE KEY-----\nexample\n"
        )


def test_allows_normal_bug_report():
    validate_outbound_prompt(
        "get_username(None) should return Guest."
    )


def test_allows_environment_variable_reference():
    validate_outbound_prompt(
        'API_KEY = os.getenv("API_KEY")'
    )


@pytest.mark.asyncio
async def test_manager_rejects_secret_before_provider_call():
    registry = ProviderRegistry()
    registry.register(FakeProvider("gemini"))
    registry.register(FakeProvider("groq"))

    manager = AIManager(
        registry=registry,
        default_provider="gemini",
        fallback_enabled=True,
        fallback_providers=("groq",),
    )

    request = AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(
                role="user",
                content='password = "example-secret-value"',
            )
        ],
    )

    with pytest.raises(AISensitiveContentError):
        await manager.generate(request)

    # Rejection occurs before any provider request or fallback.
    assert manager.health_tracker.is_available("gemini")
    assert manager.health_tracker.is_available("groq")


@pytest.mark.asyncio
async def test_manager_allows_safe_request():
    registry = ProviderRegistry()
    registry.register(FakeProvider("gemini"))

    manager = AIManager(
        registry=registry,
        default_provider="gemini",
    )

    request = AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(
                role="user",
                content="Analyze a missing None check.",
            )
        ],
    )

    response = await manager.generate(request)

    assert response.text == "Response from gemini"


def test_rejects_sensitive_json_field_after_comma():
    with pytest.raises(AISensitiveContentError):
        validate_outbound_prompt(
            '{"username": "alice", "api_key": "example-secret"}'
        )


def test_rejects_multiline_json_secret():
    with pytest.raises(AISensitiveContentError):
        validate_outbound_prompt(
            '{\n  "client_secret": "example-secret"\n}'
        )

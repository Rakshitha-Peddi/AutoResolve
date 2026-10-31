
"""Verify sensitive prompts are rejected before any provider activity."""

from unittest.mock import AsyncMock, Mock

import pytest

from ai_agent.ai.manager import AIManager
from ai_agent.ai.prompt_safety import AISensitiveContentError
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import AIMessage, AIRequest


@pytest.mark.asyncio
async def test_sensitive_prompt_never_reaches_provider_or_quota():
    primary = Mock()
    primary.name = "gemini"
    primary.generate = AsyncMock()

    fallback = Mock()
    fallback.name = "groq"
    fallback.generate = AsyncMock()

    registry = ProviderRegistry()
    registry.register(primary)
    registry.register(fallback)

    tracker = Mock()

    manager = AIManager(
        registry=registry,
        default_provider="gemini",
        fallback_enabled=True,
        fallback_providers=("groq",),
        usage_tracker=tracker,
    )

    request = AIRequest(
        task="bug_fix",
        messages=[
            AIMessage(
                role="user",
                content='password = "example-secret-value"',
            )
        ],
    )

    with pytest.raises(AISensitiveContentError):
        await manager.generate(request)

    primary.generate.assert_not_awaited()
    fallback.generate.assert_not_awaited()
    tracker.reserve_request.assert_not_called()


@pytest.mark.asyncio
async def test_all_messages_are_checked_before_provider_call():
    provider = Mock()
    provider.name = "gemini"
    provider.generate = AsyncMock()

    registry = ProviderRegistry()
    registry.register(provider)

    manager = AIManager(
        registry=registry,
        default_provider="gemini",
    )

    request = AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(
                role="system",
                content="Analyze this Python issue.",
            ),
            AIMessage(
                role="user",
                content='{"api_key": "example-secret-value"}',
            ),
        ],
    )

    with pytest.raises(AISensitiveContentError):
        await manager.generate(request)

    provider.generate.assert_not_awaited()

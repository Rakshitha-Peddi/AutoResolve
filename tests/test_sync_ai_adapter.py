
"""Tests for the synchronous AI compatibility adapter."""


import pytest
from test_ai_fallback import FakeProvider

from ai_agent.ai.manager import AIManager
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.sync_adapter import SyncAIAdapter


def make_adapter():
    registry = ProviderRegistry()
    registry.register(FakeProvider("gemini"))
    registry.register(FakeProvider("groq"))

    manager = AIManager(
        registry=registry,
        default_provider="gemini",
    )

    return SyncAIAdapter(manager)


def test_sync_adapter_returns_provider_text():
    adapter = make_adapter()

    result = adapter.generate_text(
        prompt="Analyze a Python bug.",
        task="bug_analysis",
    )

    assert result == "Response from gemini"


@pytest.mark.asyncio
async def test_async_adapter_returns_provider_text():
    adapter = make_adapter()

    result = await adapter.agenerate_text(
        prompt="Analyze a Python bug.",
        task="bug_analysis",
    )

    assert result == "Response from gemini"


@pytest.mark.asyncio
async def test_sync_call_rejected_inside_event_loop():
    adapter = make_adapter()

    with pytest.raises(
        RuntimeError,
        match="active event loop",
    ):
        adapter.generate_text(
            prompt="Find the bug.",
            task="bug_analysis",
        )


def test_adapter_preserves_task_and_token_limit():
    class RecordingManager:
        def __init__(self):
            self.request = None

        async def generate(self, request):
            self.request = request

            from ai_agent.ai.schemas import AIResponse

            return AIResponse(
                text="Generated result",
                provider="gemini",
                model="mock-model",
            )

    manager = RecordingManager()
    adapter = SyncAIAdapter(manager)

    result = adapter.generate_text(
        prompt="Fix this bug.",
        task="bug_fix",
        max_tokens=1024,
    )

    assert result == "Generated result"
    assert manager.request.task == "bug_fix"
    assert manager.request.max_tokens == 1024
    assert manager.request.messages[0].content == "Fix this bug."

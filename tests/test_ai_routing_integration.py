
import pytest
from test_ai_fallback import FakeProvider

from ai_agent.ai.manager import AIManager
from ai_agent.ai.model_router import ModelRouter
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import AIMessage, AIRequest


def make_request(task):
    return AIRequest(
        task=task,
        messages=[
            AIMessage(
                role="user",
                content="Analyze this Python code.",
            )
        ],
    )


@pytest.mark.asyncio
async def test_bug_analysis_routes_to_gemini():
    registry = ProviderRegistry()
    registry.register(FakeProvider("gemini"))
    registry.register(FakeProvider("groq"))

    router = ModelRouter(("gemini", "groq"))

    manager = AIManager(
        registry,
        default_provider="gemini",
        model_router=router,
    )

    response = await manager.generate(
        make_request("bug_analysis")
    )

    assert response.provider == "gemini"


@pytest.mark.asyncio
async def test_bug_fix_routes_to_groq():
    registry = ProviderRegistry()
    registry.register(FakeProvider("gemini"))
    registry.register(FakeProvider("groq"))

    router = ModelRouter(("gemini", "groq"))

    manager = AIManager(
        registry,
        default_provider="gemini",
        model_router=router,
    )

    response = await manager.generate(
        make_request("bug_fix")
    )

    assert response.provider == "groq"


@pytest.mark.asyncio
async def test_task_routing_fallback():
    gemini = FakeProvider("gemini")
    groq = FakeProvider("groq")

    from ai_agent.ai.exceptions import AIProviderError

    groq.error = AIProviderError("HTTP 503")

    registry = ProviderRegistry()
    registry.register(gemini)
    registry.register(groq)

    router = ModelRouter(("gemini", "groq"))

    manager = AIManager(
        registry,
        default_provider="gemini",
        fallback_enabled=True,
        model_router=router,
    )

    response = await manager.generate(
        make_request("bug_fix")
    )

    assert response.provider == "gemini"
    assert groq.calls == 1
    assert gemini.calls == 1



@pytest.mark.asyncio
async def test_disabled_provider_is_rejected():
    from ai_agent.ai.exceptions import AIConfigurationError

    registry = ProviderRegistry()
    registry.register(FakeProvider("gemini"))
    registry.register(FakeProvider("groq"))
    registry.register(FakeProvider("other"))

    router = ModelRouter(("gemini", "groq"))

    manager = AIManager(
        registry,
        default_provider="gemini",
        model_router=router,
    )

    with pytest.raises(AIConfigurationError):
        await manager.generate(
            make_request("bug_analysis"),
            provider_name="other",
        )


@pytest.mark.asyncio
async def test_explicit_provider_uses_allowed_backup():
    from ai_agent.ai.exceptions import AIProviderError

    gemini = FakeProvider("gemini")
    groq = FakeProvider(
        "groq",
        AIProviderError("Temporary outage"),
    )

    registry = ProviderRegistry()
    registry.register(gemini)
    registry.register(groq)

    router = ModelRouter(("gemini", "groq"))

    manager = AIManager(
        registry,
        default_provider="gemini",
        fallback_enabled=True,
        model_router=router,
    )

    response = await manager.generate(
        make_request("bug_analysis"),
        provider_name="groq",
    )

    assert response.provider == "gemini"
    assert groq.calls == 1
    assert gemini.calls == 1

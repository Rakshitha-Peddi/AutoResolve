
import pytest

from ai_agent.ai.exceptions import AIConfigurationError
from ai_agent.ai.model_router import ModelRouter


def test_bug_analysis_uses_gemini():
    router = ModelRouter(("gemini", "groq"))

    assert router.route("bug_analysis") == "gemini"


def test_bug_fix_uses_groq():
    router = ModelRouter(("gemini", "groq"))

    assert router.route("bug_fix") == "groq"


def test_test_generation_uses_groq():
    router = ModelRouter(("gemini", "groq"))

    assert router.route("test_generation") == "groq"


def test_unknown_task_uses_default():
    router = ModelRouter(("gemini", "groq"))

    assert router.route("unknown_task") == "gemini"


def test_disabled_provider_uses_default():
    router = ModelRouter(("gemini",))

    assert router.route("bug_fix") == "gemini"


def test_fallback_order():
    router = ModelRouter(("gemini", "groq"))

    assert router.fallback_order("bug_fix") == ("gemini",)
    assert router.fallback_order("bug_analysis") == ("groq",)


def test_custom_task_routes():
    router = ModelRouter(
        ("gemini", "groq"),
        task_routes={"bug_fix": "gemini"},
    )

    assert router.route("bug_fix") == "gemini"


def test_rejects_disabled_default():
    with pytest.raises(AIConfigurationError):
        ModelRouter(
            ("gemini",),
            default_provider="groq",
        )


def test_rejects_empty_provider_list():
    with pytest.raises(AIConfigurationError):
        ModelRouter(
            (),
            default_provider="gemini",
        )

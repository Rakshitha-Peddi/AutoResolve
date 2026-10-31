
"""Verify CodeFixEngine shares its AI adapter."""

from unittest.mock import MagicMock

from ai_agent.engine import CodeFixEngine


def test_engine_preserves_legacy_mode():
    engine = CodeFixEngine()

    assert engine.analyzer.ai_adapter is None
    assert engine.fixer.ai_adapter is None
    assert engine.test_generator.ai_adapter is None


def test_engine_shares_remote_adapter():
    adapter = MagicMock()

    engine = CodeFixEngine(ai_adapter=adapter)

    assert engine.analyzer.ai_adapter is adapter
    assert engine.fixer.ai_adapter is adapter
    assert engine.test_generator.ai_adapter is adapter


def test_engine_preserves_pipeline_order():
    engine = CodeFixEngine(ai_adapter=MagicMock())

    bug = MagicMock()
    bug.description = "Example bug"

    context = [
        (1, "app.py", "x = 1")
    ]

    analysis = {
        "root_cause": "Example issue",
        "context": [("app.py", "x = 1")],
    }

    engine.retriever.retrieve = MagicMock(
        return_value=context
    )
    engine.analyzer.analyze = MagicMock(
        return_value=analysis
    )
    engine.planner.plan = MagicMock(
        return_value="Fix plan"
    )
    engine.fixer.generate = MagicMock(
        return_value="example patch"
    )
    engine.test_generator.generate = MagicMock(
        return_value={"code": "def test_example(): pass"}
    )

    result = engine.propose_fix(
        bug,
        "/tmp/example-repository",
        feedback="Please retry",
    )

    assert result["analysis"] == analysis
    assert result["plan"] == "Fix plan"
    assert result["patch"] == "example patch"

    engine.analyzer.analyze.assert_called_once_with(
        bug, context
    )

    engine.fixer.generate.assert_called_once_with(
        "/tmp/example-repository",
        analysis,
        (
            "ORIGINAL BUG REQUIREMENTS:\n"
            "Example bug\n\n"
            "PREVIOUS VALIDATION FEEDBACK:\n"
            "Please retry"
        ),
    )

    engine.test_generator.generate.assert_called_once_with(
        bug,
        "Please retry",
        analysis["context"],
    )

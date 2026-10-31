
"""Test AI backend selection without live providers or GitHub calls."""

from unittest.mock import MagicMock

import pytest

from backend.orchestrator.real_engine import RealFixEngine


def test_legacy_backend_is_default(monkeypatch):
    monkeypatch.delenv(
        "AUTORESOLVE_AI_BACKEND",
        raising=False,
    )
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    engine = RealFixEngine()

    assert engine.code_engine.analyzer.ai_adapter is None
    assert engine.code_engine.fixer.ai_adapter is None
    assert engine.code_engine.test_generator.ai_adapter is None


def test_remote_backend_injects_shared_adapter(monkeypatch):
    monkeypatch.setenv(
        "AUTORESOLVE_AI_BACKEND",
        "remote",
    )
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    fake_manager = MagicMock()

    monkeypatch.setattr(
        "ai_agent.ai.bootstrap.build_ai_manager",
        lambda: fake_manager,
    )

    engine = RealFixEngine()

    analyzer_adapter = engine.code_engine.analyzer.ai_adapter
    fixer_adapter = engine.code_engine.fixer.ai_adapter
    generator_adapter = (
        engine.code_engine.test_generator.ai_adapter
    )

    assert analyzer_adapter is fixer_adapter
    assert fixer_adapter is generator_adapter
    assert analyzer_adapter.manager is fake_manager


def test_invalid_backend_is_rejected(monkeypatch):
    monkeypatch.setenv(
        "AUTORESOLVE_AI_BACKEND",
        "unsupported",
    )
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    with pytest.raises(
        ValueError,
        match="AUTORESOLVE_AI_BACKEND",
    ):
        RealFixEngine()


def test_missing_github_token_is_rejected(monkeypatch):
    monkeypatch.setenv(
        "AUTORESOLVE_AI_BACKEND",
        "ollama",
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(
        ValueError,
        match="GITHUB_TOKEN",
    ):
        RealFixEngine()

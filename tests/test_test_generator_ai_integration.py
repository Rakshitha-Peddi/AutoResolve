"""Verify the regression-test generator uses the AI adapter."""

import json
from types import SimpleNamespace

import pytest

from ai_agent.test_generator import RegressionTestGenerator


class FakeAIAdapter:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_text(self, prompt, task, max_tokens=2048):
        self.calls.append(
            {
                "prompt": prompt,
                "task": task,
                "max_tokens": max_tokens,
            }
        )
        return self.response


def make_bug():
    return SimpleNamespace(
        description="get_username crashes for None"
    )


def make_context():
    return [
        (
            "app.py",
            (
                "def get_username(user):\n"
                '    return user["name"]\n'
            ),
        )
    ]


def valid_response():
    return json.dumps(
        {
            "framework": "pytest",
            "path": "tests/test_regression.py",
            "summary": "Verify None returns Guest.",
            "code": (
                "from app import get_username\n\n"
                "def test_none_user():\n"
                '    assert get_username(None) == "Guest"\n'
            ),
        }
    )


def test_generator_uses_remote_adapter():
    adapter = FakeAIAdapter(valid_response())
    generator = RegressionTestGenerator(ai_adapter=adapter)

    result = generator.generate(
        make_bug(),
        context=make_context(),
    )

    assert result["framework"] == "pytest"
    assert result["path"] == "tests/test_regression.py"
    assert "test_none_user" in result["code"]

    assert len(adapter.calls) == 1
    assert adapter.calls[0]["task"] == "test_generation"
    assert adapter.calls[0]["max_tokens"] == 2048
    assert "get_username" in adapter.calls[0]["prompt"]


def test_generator_rejects_invalid_json():
    generator = RegressionTestGenerator(
        ai_adapter=FakeAIAdapter("not valid JSON")
    )

    with pytest.raises(
        RuntimeError,
        match="invalid JSON",
    ):
        generator.generate(
            make_bug(),
            context=make_context(),
        )


def test_generator_rejects_missing_fields():
    generator = RegressionTestGenerator(
        ai_adapter=FakeAIAdapter(
            json.dumps({"framework": "pytest"})
        )
    )

    with pytest.raises(
        RuntimeError,
        match="invalid 'path' field",
    ):
        generator.generate(
            make_bug(),
            context=make_context(),
        )
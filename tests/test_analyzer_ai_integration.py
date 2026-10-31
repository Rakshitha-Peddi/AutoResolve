
"""Test the Analyzer's remote-AI adapter integration."""

import json
from types import SimpleNamespace

import pytest

from ai_agent.analyzer import Analyzer


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
        description="get_username crashes when user is None"
    )


def make_context():
    return [
        (
            1,
            "app.py",
            'def get_username(user):\n    return user["name"]\n',
        )
    ]


def valid_response():
    return json.dumps(
        {
            "root_cause": (
                "The function indexes user without checking for None."
            ),
            "relevant_files": ["app.py"],
            "confidence": "high",
            "evidence": [
                'app.py contains return user["name"].'
            ],
        }
    )


def test_analyzer_uses_remote_adapter():
    adapter = FakeAIAdapter(valid_response())
    analyzer = Analyzer(ai_adapter=adapter)

    result = analyzer.analyze(
        make_bug(),
        make_context(),
    )

    assert result["confidence"] == "high"
    assert result["relevant_files"] == ["app.py"]
    assert result["context"][0][0] == "app.py"

    assert len(adapter.calls) == 1
    assert adapter.calls[0]["task"] == "bug_analysis"
    assert adapter.calls[0]["max_tokens"] == 2048
    assert "get_username" in adapter.calls[0]["prompt"]


def test_analyzer_rejects_unknown_source_file():
    response = json.dumps(
        {
            "root_cause": "Missing None check.",
            "relevant_files": ["invented.py"],
            "confidence": "high",
            "evidence": ["The code accesses user directly."],
        }
    )

    analyzer = Analyzer(
        ai_adapter=FakeAIAdapter(response)
    )

    with pytest.raises(
        RuntimeError,
        match="not retrieved",
    ):
        analyzer.analyze(
            make_bug(),
            make_context(),
        )


def test_analyzer_rejects_invalid_json():
    analyzer = Analyzer(
        ai_adapter=FakeAIAdapter("not valid JSON")
    )

    with pytest.raises(
        RuntimeError,
        match="invalid JSON",
    ):
        analyzer.analyze(
            make_bug(),
            make_context(),
        )


def test_analyzer_rejects_invalid_confidence():
    response = json.dumps(
        {
            "root_cause": "Missing None check.",
            "relevant_files": ["app.py"],
            "confidence": "certain",
            "evidence": ["Missing validation."],
        }
    )

    analyzer = Analyzer(
        ai_adapter=FakeAIAdapter(response)
    )

    with pytest.raises(
        RuntimeError,
        match="confidence",
    ):
        analyzer.analyze(
            make_bug(),
            make_context(),
        )

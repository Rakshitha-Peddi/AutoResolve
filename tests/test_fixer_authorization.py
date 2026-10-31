
"""Verify that the AI Fixer cannot modify unauthorized files."""

import json

import pytest

from ai_agent.fixer import Fixer


class FakeAIAdapter:
    def __init__(self, file_path, corrected_code):
        self.file_path = file_path
        self.corrected_code = corrected_code

    def generate_text(self, prompt, task, max_tokens=2048):
        return json.dumps({
            "summary": "Proposed correction",
            "root_cause": "Missing input validation",
            "file_path": self.file_path,
            "corrected_code": self.corrected_code,
        })


def test_fixer_rejects_file_not_in_retrieved_context(tmp_path):
    (tmp_path / "app.py").write_text(
        "def process(value):\n    return value\n"
    )

    (tmp_path / "config.py").write_text(
        "DEBUG = False\n"
    )

    adapter = FakeAIAdapter(
        "config.py",
        "DEBUG = True\n",
    )

    analysis = {
        "root_cause": "Missing input validation",
        "context": [
            (
                "app.py",
                "def process(value):\n    return value\n",
            )
        ],
    }

    with pytest.raises(
        RuntimeError,
        match="not retrieved",
    ):
        Fixer(ai_adapter=adapter).generate(
            tmp_path,
            analysis,
        )

    assert (tmp_path / "config.py").read_text() == (
        "DEBUG = False\n"
    )


def test_fixer_rejects_sensitive_source(tmp_path):
    source = (
        'API_KEY = "example-secret-value"\n'
        "def process(value):\n"
        "    return value\n"
    )

    (tmp_path / "app.py").write_text(source)

    adapter = FakeAIAdapter(
        "app.py",
        source.replace(
            "return value",
            "return str(value)",
        ),
    )

    analysis = {
        "root_cause": "Input handling issue",
        "context": [("app.py", source)],
    }

    with pytest.raises(
        RuntimeError,
        match="sensitive content",
    ):
        Fixer(ai_adapter=adapter).generate(
            tmp_path,
            analysis,
        )


def test_fixer_allows_retrieved_safe_source(tmp_path):
    source = "def process(value):\n    return value\n"
    corrected = (
        "def process(value):\n"
        "    if value is None:\n"
        "        return 0\n"
        "    return value\n"
    )

    (tmp_path / "app.py").write_text(source)

    adapter = FakeAIAdapter("app.py", corrected)

    analysis = {
        "root_cause": "Missing None guard",
        "context": [("app.py", source)],
    }

    patch = Fixer(ai_adapter=adapter).generate(
        tmp_path,
        analysis,
    )

    assert "diff --git a/app.py b/app.py" in patch
    assert "+    if value is None:" in patch

    # Generating a patch must not alter repository files.
    assert (tmp_path / "app.py").read_text() == source

def test_fixer_rejects_source_changed_after_retrieval(tmp_path):
    original = "def process(value):\n    return value\n"

    (tmp_path / "app.py").write_text(
        original,
        encoding="utf-8",
    )

    analysis = {
        "root_cause": "Missing None guard",
        "context": [("app.py", original)],
    }

    # Simulate the source changing after the Retriever ran.
    (tmp_path / "app.py").write_text(
        "def process(value):\n    return str(value)\n",
        encoding="utf-8",
    )

    adapter = FakeAIAdapter(
        "app.py",
        "def process(value):\n    return 0\n",
    )

    with pytest.raises(
        RuntimeError,
        match="source file changed",
    ):
        Fixer(ai_adapter=adapter).generate(
            tmp_path,
            analysis,
        )
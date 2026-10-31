
"""Tests for remote AI integration with the existing Fixer."""

import json

import pytest

from ai_agent.fixer import Fixer


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


def create_source(tmp_path):
    source = tmp_path / "app.py"
    source.write_text(
        'def get_username(user):\n'
        '    return user["name"]\n',
        encoding="utf-8",
    )
    return source


def valid_ai_response():
    return json.dumps(
        {
            "summary": "Handle missing users.",
            "root_cause": "Missing None check.",
            "file_path": "app.py",
            "corrected_code": (
                "def get_username(user):\n"
                "    if user is None:\n"
                '        return "Guest"\n'
                '    return user["name"]\n'
            ),
        }
    )


def make_analysis():
    return {
        "root_cause": "Missing None check.",
        "context": [
    (
        "app.py",
        (
            'def get_username(user):\n'
            '    return user["name"]\n'
        ),
    )
],
    }


def test_fixer_uses_remote_adapter(tmp_path):
    create_source(tmp_path)

    adapter = FakeAIAdapter(valid_ai_response())
    fixer = Fixer(ai_adapter=adapter)

    patch = fixer.generate(
        tmp_path,
        make_analysis(),
    )

    assert "diff --git a/app.py b/app.py" in patch
    assert "+    if user is None:" in patch

    assert len(adapter.calls) == 1
    assert adapter.calls[0]["task"] == "bug_fix"
    assert adapter.calls[0]["max_tokens"] == 2048

    # Generating a patch should not modify the original file.
    assert "if user is None" not in (
        tmp_path / "app.py"
    ).read_text(encoding="utf-8")


def test_fixer_rejects_unsafe_file_path(tmp_path):
    create_source(tmp_path)

    response = json.dumps(
        {
            "summary": "Unsafe change.",
            "root_cause": "Missing None check.",
            "file_path": "../outside.py",
            "corrected_code": "x = 1\n",
        }
    )

    fixer = Fixer(
        ai_adapter=FakeAIAdapter(response)
    )

    with pytest.raises(RuntimeError, match="unsafe"):
        fixer.generate(tmp_path, make_analysis())


def test_fixer_rejects_invalid_python(tmp_path):
    create_source(tmp_path)

    response = json.dumps(
        {
            "summary": "Invalid change.",
            "root_cause": "Missing None check.",
            "file_path": "app.py",
            "corrected_code": "def broken(:\n",
        }
    )

    fixer = Fixer(
        ai_adapter=FakeAIAdapter(response)
    )

    with pytest.raises(RuntimeError, match="invalid Python"):
        fixer.generate(tmp_path, make_analysis())


def test_fixer_rejects_unchanged_code(tmp_path):
    create_source(tmp_path)

    response = json.dumps(
        {
            "summary": "No change.",
            "root_cause": "Missing None check.",
            "file_path": "app.py",
            "corrected_code": (
                'def get_username(user):\n'
                '    return user["name"]\n'
            ),
        }
    )

    fixer = Fixer(
        ai_adapter=FakeAIAdapter(response)
    )

    with pytest.raises(RuntimeError, match="did not change"):
        fixer.generate(tmp_path, make_analysis())

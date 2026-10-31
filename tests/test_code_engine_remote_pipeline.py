
"""Test the complete AI generation pipeline without external APIs."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_agent.engine import CodeFixEngine

ORIGINAL_CODE = (
    "def get_username(user):\n"
    '    return user["name"]\n'
)

FIXED_CODE = (
    "def get_username(user):\n"
    "    if user is None:\n"
    '        return "Guest"\n'
    '    return user["name"]\n'
)


class ScriptedAIAdapter:
    """Return task-specific responses while recording requests."""

    def __init__(self):
        self.calls = []

    def generate_text(self, prompt, task, max_tokens=2048):
        self.calls.append(task)

        if task == "bug_analysis":
            return json.dumps({
                "root_cause": "Missing None check before dictionary access.",
                "relevant_files": ["app.py"],
                "confidence": "high",
                "evidence": [
                    'app.py indexes user using user["name"].'
                ],
            })

        if task == "bug_fix":
            return json.dumps({
                "summary": "Return Guest for missing users.",
                "root_cause": "Missing None check.",
                "file_path": "app.py",
                "corrected_code": FIXED_CODE,
            })

        if task == "test_generation":
            return json.dumps({
                "framework": "pytest",
                "path": "tests/test_regression.py",
                "summary": "Verify a missing user returns Guest.",
                "code": (
                    "from app import get_username\n\n"
                    "def test_none_user():\n"
                    '    assert get_username(None) == "Guest"\n'
                ),
            })

        raise AssertionError(f"Unexpected AI task: {task}")


def test_full_remote_ai_generation_pipeline(tmp_path):
    source_file = tmp_path / "app.py"
    source_file.write_text(ORIGINAL_CODE, encoding="utf-8")

    adapter = ScriptedAIAdapter()
    engine = CodeFixEngine(ai_adapter=adapter)

    # Keep real analysis, fixing and test generation.
    # Mock retrieval and planning to isolate the AI pipeline.
    engine.retriever.retrieve = MagicMock(
        return_value=[(1, "app.py", ORIGINAL_CODE)]
    )
    engine.planner.plan = MagicMock(
        return_value=["Add a None guard in app.py"]
    )

    bug = SimpleNamespace(
        description="get_username crashes when user is None"
    )

    result = engine.propose_fix(bug, tmp_path)

    assert adapter.calls == [
        "bug_analysis",
        "bug_fix",
        "test_generation",
    ]

    assert result["analysis"]["confidence"] == "high"
    assert result["analysis"]["relevant_files"] == ["app.py"]

    assert "diff --git a/app.py b/app.py" in result["patch"]
    assert "+    if user is None:" in result["patch"]

    assert result["tests"]["framework"] == "pytest"
    assert "test_none_user" in result["tests"]["code"]

    # Patch generation must not modify the source file directly.
    assert source_file.read_text(encoding="utf-8") == ORIGINAL_CODE

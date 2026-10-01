from unittest.mock import Mock, patch

from backend.orchestrator.ai_engine import AIBugEngine


def test_ai_engine_returns_analysis():
    repository_files = [
        {
            "path": "example.py",
            "content": """
def divide(a, b):
    return a / b
""",
        }
    ]

    fake_response = Mock()
    fake_response.output_text = """
{
    "bug_found": true,
    "root_cause": "Division by zero occurs when b is zero.",
    "affected_files": ["example.py"],
    "proposed_changes": [
        "Validate b before performing the division."
    ],
    "patch_plan": [
        "Add a zero-value check for b.",
        "Add a regression test for division by zero."
    ],
    "confidence": "high"
}
"""

    with patch("backend.orchestrator.ai_engine.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_client.responses.create.return_value = fake_response

        engine = AIBugEngine(api_key="test-key")

        result = engine.analyze_bug(
            bug_name="Division by zero",
            bug_description="The application crashes when b is zero.",
            repository_files=repository_files,
        )

    assert result["bug_found"] is True
    assert result["root_cause"]
    assert result["affected_files"] == ["example.py"]
    assert result["proposed_changes"]
    assert result["patch_plan"]
    assert result["confidence"] == "high"

    mock_client.responses.create.assert_called_once()
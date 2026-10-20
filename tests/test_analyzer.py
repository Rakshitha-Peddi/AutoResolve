
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from ai_agent.analyzer import Analyzer


def test_analyzer_returns_root_cause_and_source_evidence():
    fake_response = json.dumps(
        {
            "root_cause": "find_user returns None when the user is missing.",
            "relevant_files": ["user_service.py"],
            "confidence": "high",
            "evidence": [
                "The source checks whether user is None and returns None."
            ],
        }
    )

    context = [
        (
            3,
            "user_service.py",
            "def find_user(user_id):\n"
            "    user = database_lookup(user_id)\n"
            "    if user is None:\n"
            "        return None\n",
        )
    ]

    with patch("ai_agent.analyzer.generate_text") as mock_openai:
        mock_generate = mock_openai
        mock_generate.return_value = fake_response

        analyzer = Analyzer.__new__(Analyzer)
        analyzer.model = "test-model"

        result = analyzer.analyze(
            SimpleNamespace(
                description="Missing users are not handled correctly."
            ),
            context,
        )

    assert result["root_cause"]
    assert result["relevant_files"] == ["user_service.py"]
    assert result["confidence"] == "high"
    assert result["evidence"]
    assert result["context"] == [
        ("user_service.py", context[0][2])
    ]

    prompt = mock_generate.call_args.args[0]
    assert "user_service.py" in prompt
    assert "database_lookup" in prompt
    mock_generate.assert_called_once()


def test_analyzer_rejects_invalid_json():
    fake_response = "This is not JSON"

    with patch("ai_agent.analyzer.generate_text") as mock_openai:
        mock_generate = mock_openai
        mock_generate.return_value = fake_response

        analyzer = Analyzer.__new__(Analyzer)
        analyzer.model = "test-model"

        with pytest.raises(
            RuntimeError,
            match="AI analyzer returned invalid JSON",
        ):
            analyzer.analyze(
                SimpleNamespace(description="A reported bug"),
                [(1, "example.py", "def example(): pass")],
            )




@pytest.mark.parametrize(
    "response_text, expected_error",
    [
        (
            '{"root_cause": "Missing field checks"}',
            "invalid 'relevant_files' field",
        ),
        (
            json.dumps({
                "root_cause": "The user lookup mishandles None.",
                "relevant_files": ["user_service.py"],
                "confidence": "certain",
                "evidence": ["The function returns None."],
            }),
            "invalid confidence level",
        ),
        (
            json.dumps({
                "root_cause": "The user lookup mishandles None.",
                "relevant_files": ["user_service.py"],
                "confidence": "high",
                "evidence": [],
            }),
            "invalid evidence",
        ),
    ],
)
def test_analyzer_validates_response_fields(
    response_text, expected_error
):
    fake_response = response_text

    with patch("ai_agent.analyzer.generate_text") as mock_openai:
        mock_generate = mock_openai
        mock_generate.return_value = fake_response

        analyzer = Analyzer.__new__(Analyzer)
        analyzer.model = "test-model"
        with pytest.raises(RuntimeError, match=expected_error):
            analyzer.analyze(
                SimpleNamespace(description="A reported bug"),
                [(1, "user_service.py", "return None")],
            )


def test_analyzer_rejects_files_not_in_retrieved_context():
    fake_response = json.dumps({
        "root_cause": "The user lookup mishandles None.",
        "relevant_files": ["secret_file.py"],
        "confidence": "high",
        "evidence": ["The retrieved function returns None."],
    })

    with patch("ai_agent.analyzer.generate_text") as mock_openai:
        mock_generate = mock_openai
        mock_generate.return_value = fake_response

        analyzer = Analyzer.__new__(Analyzer)
        analyzer.model = "test-model"

        with pytest.raises(
            RuntimeError,
            match="files that were not retrieved",
        ):
            analyzer.analyze(
                SimpleNamespace(description="A reported bug"),
                [
                    (
                        1,
                        "user_service.py",
                        "def find_user():\n    return None\n",
                    )
                ],
            )

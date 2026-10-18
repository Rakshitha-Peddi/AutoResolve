
import json
from unittest.mock import Mock, patch

import pytest

from ai_agent.test_generator import RegressionTestGenerator


def run_generator_with_response(response_text):
    fake_response = Mock()
    fake_response.output_text = response_text

    with patch("ai_agent.test_generator.OpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_client.responses.create.return_value = fake_response

        generator = RegressionTestGenerator.__new__(
            RegressionTestGenerator
        )
        generator.client = mock_client
        generator.model = "test-model"

        class Bug:
            description = "Handle a missing user safely."

        return generator.generate(Bug())


def test_generator_accepts_valid_response():
    response = json.dumps({
        "framework": "pytest",
        "path": "tests/test_regression.py",
        "summary": "Tests missing-user handling",
        "code": (
            "def test_missing_user():\n"
            "    assert lookup_user(None) is None\n"
        ),
    })

    result = run_generator_with_response(response)

    assert result["framework"] == "pytest"
    assert result["path"] == "tests/test_regression.py"
    assert "def test_missing_user" in result["code"]


@pytest.mark.parametrize(
    "response_text",
    [
        "not JSON",
        "[]",
        "null",
        "42",
        '"plain text"',
    ],
)
def test_generator_rejects_invalid_response_structure(response_text):
    with pytest.raises(RuntimeError):
        run_generator_with_response(response_text)


@pytest.mark.parametrize(
    "field",
    ["framework", "path", "summary", "code"],
)
def test_generator_rejects_missing_or_empty_fields(field):
    response_data = {
        "framework": "pytest",
        "path": "tests/test_regression.py",
        "summary": "Tests missing-user handling",
        "code": "def test_missing_user():\n    assert True\n",
    }
    response_data[field] = ""

    with pytest.raises(RuntimeError):
        run_generator_with_response(json.dumps(response_data))




@pytest.mark.parametrize(
    "field, invalid_value",
    [
        ("framework", 123),
        ("path", 123),
        ("summary", 123),
        ("code", 123),
        ("framework", []),
        ("path", {}),
        ("summary", None),
        ("code", []),
    ],
)
def test_generator_rejects_fields_with_invalid_types(
    field,
    invalid_value,
):
    response_data = {
        "framework": "pytest",
        "path": "tests/test_regression.py",
        "summary": "Tests missing-user handling",
        "code": "def test_missing_user():\n    assert True\n",
    }
    response_data[field] = invalid_value

    with pytest.raises(RuntimeError):
        run_generator_with_response(json.dumps(response_data))

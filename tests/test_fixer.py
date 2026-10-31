import json
from unittest.mock import patch

import pytest

from ai_agent.fixer import Fixer


def run_fixer_with_response(response_text, tmp_path):
    source = tmp_path / "example.py"
    source.write_text("old_value = 1\n", encoding="utf-8")

    with patch("ai_agent.fixer.generate_text", return_value=response_text):
        fixer = Fixer.__new__(Fixer)
        fixer.model = "test-model"
        return fixer.generate(
            repo_path=str(tmp_path),
            analysis={
                "root_cause": "Example cause",
                "context": [
                    (
                        "example.py",
                        (tmp_path / "example.py").read_text(
                            encoding="utf-8"
                        ),
                    )
                ],
            }
        )


def valid_response():
    return json.dumps({
        "summary": "Correct the value",
        "root_cause": "The value was incorrect",
        "file_path": "example.py",
        "corrected_code": "old_value = 2\n",
    })


def test_fixer_accepts_valid_json_and_returns_patch(tmp_path):
    patch_text = run_fixer_with_response(valid_response(), tmp_path)

    assert "--- a/example.py" in patch_text
    assert "+++ b/example.py" in patch_text
    assert "-old_value = 1" in patch_text
    assert "+old_value = 2" in patch_text


@pytest.mark.parametrize(
    "response_text, expected_error",
    [
        ("not JSON", "invalid JSON"),
        ("[]", "invalid response structure"),
        (
            json.dumps({
                "root_cause": "Example",
                "file_path": "example.py",
                "corrected_code": "old_value = 2\n",
            }),
            "invalid 'summary' field",
        ),
        (
            json.dumps({
                "summary": "Example",
                "root_cause": "",
                "file_path": "example.py",
                "corrected_code": "old_value = 2\n",
            }),
            "invalid 'root_cause' field",
        ),
        (
            json.dumps({
                "summary": "Example",
                "root_cause": "Example cause",
                "file_path": "example.py",
                "corrected_code": "",
            }),
            "invalid 'corrected_code' field",
        ),
    ],
)
def test_fixer_rejects_invalid_json_fields(
    response_text, expected_error, tmp_path
):
    with pytest.raises(RuntimeError, match=expected_error):
        run_fixer_with_response(response_text, tmp_path)


def test_fixer_rejects_unsafe_source_path(tmp_path):
    response = json.dumps({
        "summary": "Attempted fix",
        "root_cause": "Example cause",
        "file_path": "../outside.py",
        "corrected_code": "old_value = 2\n",
    })

    with pytest.raises(RuntimeError, match="unsafe source file"):
        run_fixer_with_response(response, tmp_path)


def test_fixer_rejects_invalid_python(tmp_path):
    response = json.dumps({
        "summary": "Attempted fix",
        "root_cause": "Example cause",
        "file_path": "example.py",
        "corrected_code": "def broken(:\n",
    })

    with pytest.raises(RuntimeError, match="invalid Python"):
        run_fixer_with_response(response, tmp_path)


import json
from unittest.mock import Mock, patch

import pytest

from ai_agent.fixer import Fixer


def run_fixer_with_response(response_text):
    fake_response = response_text

    with patch("ai_agent.fixer.generate_text") as mock_openai:
        mock_generate = mock_openai
        mock_generate.return_value = fake_response

        fixer = Fixer.__new__(Fixer)
        fixer.model = "test-model"

        return fixer.generate(
            repo_path="/tmp/fake-repo",
            analysis={"root_cause": "Example cause", "context": []},
        )


def test_fixer_accepts_valid_json_and_returns_patch():
    patch_text = (
        "--- a/example.py\n"
        "+++ b/example.py\n"
        "@@ -1 +1 @@\n"
        "-old_value = 1\n"
        "+old_value = 2\n"
    )

    response = json.dumps({
        "summary": "Correct the value",
        "root_cause": "The value was incorrect",
        "patch": patch_text,
    })

    assert run_fixer_with_response(response) == patch_text.strip()


@pytest.mark.parametrize(
    "response_text, expected_error",
    [
        ("not JSON", "invalid JSON"),
        ("[]", "invalid response structure"),
        (
            json.dumps({"root_cause": "Example", "patch": "diff"}),
            "invalid 'summary' field",
        ),
        (
            json.dumps({
                "summary": "Example",
                "root_cause": "",
                "patch": "diff",
            }),
            "invalid 'root_cause' field",
        ),
        (
            json.dumps({
                "summary": "Example",
                "root_cause": "Example cause",
                "patch": "",
            }),
            "invalid 'patch' field",
        ),
    ],
)
def test_fixer_rejects_invalid_json_fields(
    response_text, expected_error
):
    with pytest.raises(RuntimeError, match=expected_error):
        run_fixer_with_response(response_text)



def test_fixer_rejects_patch_without_diff_content():
    response = json.dumps({
        "summary": "Attempted fix",
        "root_cause": "Example cause",
        "patch": (
            "--- a/example.py\n"
            "+++ b/example.py\n"
            "This is not a valid unified diff.\n"
        ),
    })

    with pytest.raises(
        RuntimeError,
        match="valid unified diff",
    ):
        run_fixer_with_response(response)



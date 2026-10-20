import json
import os

from .ollama_client import generate_text

from ._json import parse_model_json


class RegressionTestGenerator:
    """Generate regression-test code for a reported bug."""

    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

    def generate(self, bug, feedback="", context=None):
        repository_code = "\n\n".join(
            f"FILE: {path}\n{content}"
            for path, content in (context or [])
        ) or "(not available)"

        prompt = f"""
You are the regression-test component of AutoResolve.

Generate a focused regression test for this bug.

BUG:
{bug.description}

DEVELOPER FEEDBACK:
{feedback or "None"}

REPOSITORY CODE (use these real module paths and function names in imports):
{repository_code}

Requirements:

1. Reproduce the reported failure.
2. Verify the expected corrected behavior.
3. Follow the repository's existing testing conventions.
   The test file path MUST start with tests/ and must import only modules that exist above.
   The test must FAIL on the current (unfixed) code and PASS once the bug is fixed.
4. Do not test unrelated behavior.
5. Return a complete test file or a complete test function.
6. Use pytest unless the bug clearly requires another framework.
7. Do not use Markdown code fences.

Return ONLY valid JSON:

{{
  "framework": "pytest",
  "path": "tests/test_regression.py",
  "summary": "what the regression test verifies",
  "code": "complete Python test code"
}}
"""

        text = generate_text(prompt, self.model)

        try:
            result = parse_model_json(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AI test generator returned invalid JSON."
            ) from exc

        if not isinstance(result, dict):
            raise RuntimeError(
                "AI test generator returned an invalid response structure."
            )


        required = ("framework", "path", "summary", "code")

        for field in required:
            value = result.get(field)

            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(
                    f"AI test generator returned an invalid '{field}' field."
                )

        return result

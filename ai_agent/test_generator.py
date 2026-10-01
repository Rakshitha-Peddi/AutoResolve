import json
import os

from openai import OpenAI


class RegressionTestGenerator:
    """Generate regression-test code for a reported bug."""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")

        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.6")

    def generate(self, bug, feedback=""):
        prompt = f"""
You are the regression-test component of AutoResolve.

Generate a focused regression test for this bug.

BUG:
{bug.description}

DEVELOPER FEEDBACK:
{feedback or "None"}

Requirements:

1. Reproduce the reported failure.
2. Verify the expected corrected behavior.
3. Follow the repository's existing testing conventions.
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

        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )

        text = response.output_text.strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AI test generator returned invalid JSON."
            ) from exc

        required = ("framework", "path", "summary", "code")

        for field in required:
            if not result.get(field):
                raise RuntimeError(
                    f"AI test generator returned no '{field}'."
                )

        return result
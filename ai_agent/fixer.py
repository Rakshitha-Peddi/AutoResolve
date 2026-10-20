import json
import os

from .ollama_client import generate_text

from ._json import parse_model_json


class Fixer:
    """Generate repository-specific patches using an AI coding model."""

    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

    def generate(self, repo_path, analysis, feedback=""):
        context = analysis.get("context", [])

        files_text = "\n\n".join(
            f"FILE: {path}\n{content}"
            for path, content in context
        )

        prompt = f"""
You are the coding agent for AutoResolve.

Your job is to fix the reported software bug in the supplied repository.

BUG ANALYSIS:
{json.dumps(analysis, indent=2)}

DEVELOPER FEEDBACK:
{feedback or "None"}

REPOSITORY CONTEXT:
{files_text}

Rules:

1. Identify the actual cause of the bug from the supplied code.
2. Make the smallest safe change that fixes the bug.
3. Do not rewrite unrelated code.
4. Preserve existing public APIs unless the bug requires otherwise.
5. Include regression-test changes when appropriate.
6. Return a valid unified git diff.
7. The diff must be directly applicable with:

   git apply

8. Use repository-relative paths.
9. Do not use Markdown code fences.
10. Do not explain the patch outside the JSON response.

Return ONLY valid JSON in this exact shape:

{{
  "summary": "short explanation of the fix",
  "root_cause": "actual root cause",
  "patch": "complete unified git diff"
}}
"""

        text = generate_text(prompt, self.model)


        try:
            result = parse_model_json(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AI fixer returned invalid JSON."
            ) from exc

        if not isinstance(result, dict):
            raise RuntimeError(
                "AI fixer returned an invalid response structure."
            )

        for field in ("summary", "root_cause", "patch"):
            if (
                not isinstance(result.get(field), str)
                or not result[field].strip()
            ):
                raise RuntimeError(
                    f"AI fixer returned an invalid '{field}' field."
                )

        patch = result["patch"].strip()

        if not patch:
            raise RuntimeError(
                "AI fixer returned an empty patch."
            )


        import re

        if "--- " not in patch or "+++ " not in patch:
            raise RuntimeError(
                "AI fixer did not return a valid unified diff."
            )

        if not re.search(
            r"(?m)^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@",
            patch,
        ):
            raise RuntimeError(
                "AI fixer did not return a valid unified diff."
            )

        diff_lines = patch.splitlines()
        if not any(
            line.startswith("+") and not line.startswith("+++")
            for line in diff_lines
        ) or not any(
            line.startswith("-") and not line.startswith("---")
            for line in diff_lines
        ):
            raise RuntimeError(
                "AI fixer did not return a valid unified diff."
            )

        return patch

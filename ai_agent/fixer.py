import json
import os

from openai import OpenAI


class Fixer:
    """Generate repository-specific patches using an AI coding model."""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")

        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.6")

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

        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )

        text = response.output_text.strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AI fixer returned invalid JSON."
            ) from exc

        patch = result.get("patch", "").strip()

        if not patch:
            raise RuntimeError(
                "AI fixer returned an empty patch."
            )

        if "--- " not in patch or "+++ " not in patch:
            raise RuntimeError(
                "AI fixer did not return a valid unified diff."
            )

        return patch

import json
import os

from openai import OpenAI


class AIBugEngine:
    """Analyze repository bugs and propose fixes using OpenAI."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")

        self.client = OpenAI(api_key=self.api_key)

    def analyze_bug(
        self,
        bug_name: str,
        bug_description: str,
        repository_files: list[dict],
    ) -> dict:
        files_text = "\n\n".join(
            f"FILE: {file['path']}\n{file['content']}"
            for file in repository_files
        )

        prompt = f"""
You are AutoResolve, an autonomous software bug analysis agent.

Analyze the following bug against the supplied repository files.

BUG NAME:
{bug_name}

BUG DESCRIPTION:
{bug_description}

REPOSITORY FILES:
{files_text}

Determine:

1. Whether the supplied repository appears to contain the reported bug.
2. The likely root cause.
3. Which files need to change.
4. What changes should be made.
5. A concrete patch plan.

Do NOT claim that code was changed.
Do NOT claim that tests passed.
Do NOT invent files or repository behavior.

Return ONLY valid JSON using exactly this structure:

{{
  "bug_found": true,
  "root_cause": "string",
  "affected_files": ["string"],
  "proposed_changes": ["string"],
  "patch_plan": ["string"],
  "confidence": "high"
}}
"""

        response = self.client.responses.create(
            model="gpt-5.6",
            input=prompt,
        )

        text = response.output_text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AI returned invalid JSON."
            ) from exc
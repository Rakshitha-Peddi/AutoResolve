import os
import json

from openai import OpenAI


class Analyzer:
    """Analyze a bug using the relevant repository source code."""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")

        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.6")

    def analyze(self, bug, context):
        repository_context = "\n\n".join(
            f"FILE: {path}\n{content}"
            for _, path, content in context
        )

        prompt = f"""
You are the bug-analysis component of AutoResolve.

Analyze the reported software bug using the supplied repository code.

BUG:
{bug.description}

REPOSITORY CODE:
{repository_context}

Determine:

1. The likely root cause.
2. Which files/functions are relevant.
3. Evidence in the source code supporting the diagnosis.
4. Your confidence level.

Do not invent files or code that are not present.

Return ONLY valid JSON:

{{
  "root_cause": "specific technical explanation",
  "relevant_files": ["path/to/file.py"],
  "confidence": "high",
  "evidence": [
    "specific evidence from the supplied code"
  ]
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
                "AI analyzer returned invalid JSON."
            ) from exc

        result["context"] = [
            (path, content)
            for _, path, content in context
        ]

        return result
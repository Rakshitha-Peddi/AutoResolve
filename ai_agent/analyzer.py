import os
import json

from .ollama_client import generate_text

from ._json import parse_model_json


class Analyzer:
    """Analyze a bug using the relevant repository source code."""

    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

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

        text = generate_text(prompt, self.model)


        try:
            result = parse_model_json(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AI analyzer returned invalid JSON."
            ) from exc

        if not isinstance(result, dict):
            raise RuntimeError(
                "AI analyzer returned an invalid response structure."
            )

        required_fields = {
            "root_cause": str,
            "relevant_files": list,
            "confidence": str,
            "evidence": list,
        }

        for field, expected_type in required_fields.items():
            if field not in result or not isinstance(
                result[field], expected_type
            ):
                raise RuntimeError(
                    f"AI analyzer returned an invalid '{field}' field."
                )

        if not result["root_cause"].strip():
            raise RuntimeError(
                "AI analyzer returned an empty root cause."
            )

        if not all(
            isinstance(path, str) and path.strip()
            for path in result["relevant_files"]
        ):
            raise RuntimeError(
                "AI analyzer returned invalid relevant files."
            )

        if not result["evidence"] or not all(
            isinstance(item, str) and item.strip()
            for item in result["evidence"]
        ):
            raise RuntimeError(
                "AI analyzer returned invalid evidence."
            )
        retrieved_paths = {
            path for _, path, _ in context
        }

        unsupported_files = [
            path for path in result["relevant_files"]
            if path not in retrieved_paths
        ]

        if unsupported_files:
            raise RuntimeError(
                "AI analyzer referenced files that were not retrieved."
            )
        if result["confidence"] not in {
            "low", "medium", "high"
        }:
            raise RuntimeError(
                "AI analyzer returned an invalid confidence level."
            )
        result["context"] = [
            (path, content)
            for _, path, content in context
        ]

        return result
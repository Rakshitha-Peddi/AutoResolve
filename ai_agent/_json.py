"""Tolerant JSON parsing for model replies.

Models often wrap JSON in ```json fences or add a sentence before/after it.
Strict ``json.loads`` then fails and the whole repair attempt is lost.
"""
import json
import re

_FENCE = re.compile(r"^```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def parse_model_json(text: str):
    """Parse JSON from a model reply. Raises json.JSONDecodeError if impossible."""
    text = (text or "").strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise

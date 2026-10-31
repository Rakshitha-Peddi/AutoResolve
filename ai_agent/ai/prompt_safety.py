
"""Block recognizable credentials before sending prompts to remote AI."""

import re


class AISensitiveContentError(ValueError):
    """An outbound AI request contains potentially sensitive content."""


SECRET_PATTERNS = (
    # Private-key material.
    re.compile(
        r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
        re.IGNORECASE,
    ),
    # Common provider token formats.
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    # Hardcoded sensitive assignments, including quoted JSON keys.

    # Hardcoded assignments and JSON-style sensitive fields.
    re.compile(
        r"""(?im)(?:^|[{,])[ \t]*["']?"""
        r"(?:api_key|apikey|access_token|auth_token|"
        r"secret_key|client_secret|github_token|"
        r"gemini_api_key|groq_api_key|"
        r"database_password|password|passwd|private_key)"
        r"""["']?[ \t]*(?:=|:)[ \t]*["'][^"'\r\n]+["']"""
    ),

)


def validate_outbound_prompt(content: str) -> None:
    """Reject recognizable secrets without logging their contents."""
    for pattern in SECRET_PATTERNS:
        if pattern.search(content):
            raise AISensitiveContentError(
                "Outbound AI request blocked: potentially sensitive "
                "content detected. Review the input before retrying."
            )

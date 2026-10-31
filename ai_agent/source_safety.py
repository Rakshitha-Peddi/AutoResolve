
"""Conservative checks for sensitive content in Python source files."""

import ast
import re

SENSITIVE_NAMES = frozenset({
    "api_key",
    "apikey",
    "access_token",
    "auth_token",
    "secret_key",
    "client_secret",
    "password",
    "passwd",
    "private_key",
    "github_token",
    "gemini_api_key",
    "groq_api_key",
    "database_password",
})

SENSITIVE_PATTERNS = (
    re.compile(
        r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
    ),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
)


def _sensitive_name(name: str) -> bool:
    normalized = name.lower().strip("_")
    return normalized in SENSITIVE_NAMES or normalized.endswith(
        (
            "_api_key",
            "_secret_key",
            "_access_token",
            "_password",
        )
    )


def _hardcoded_value(value: ast.expr) -> bool:
    if isinstance(value, ast.Constant):
        return isinstance(value.value, (str, bytes)) and bool(value.value)

    return isinstance(value, ast.JoinedStr)


def _target_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]

    if isinstance(target, ast.Attribute):
        return [target.attr]

    if isinstance(target, (ast.Tuple, ast.List)):
        return [
            name
            for item in target.elts
            for name in _target_names(item)
        ]

    return []


def contains_sensitive_source(source: str) -> bool:
    """Reject sources with recognizable embedded credentials.

    Returns True for code that cannot be parsed, avoiding
    transmission of uninspected content to remote AI providers.
    """
    if any(pattern.search(source) for pattern in SENSITIVE_PATTERNS):
        return True

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return True

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if _hardcoded_value(node.value) and any(
                _sensitive_name(name)
                for target in node.targets
                for name in _target_names(target)
            ):
                return True

        elif isinstance(node, ast.AnnAssign):
            if (
                node.value is not None
                and _hardcoded_value(node.value)
                and any(
                    _sensitive_name(name)
                    for name in _target_names(node.target)
                )
            ):
                return True

        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and _sensitive_name(key.value)
                    and _hardcoded_value(value)
                ):
                    return True

    return False

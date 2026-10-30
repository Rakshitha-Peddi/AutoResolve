
"""Build AutoResolve's configured AI manager."""

import os
from pathlib import Path

from .exceptions import AIConfigurationError
from .manager import AIManager
from .model_router import ModelRouter
from .providers.gemini import GeminiProvider
from .providers.groq import GroqProvider
from .registry import ProviderRegistry
from .sqlite_usage_tracker import SQLiteUsageTracker

SUPPORTED_PROVIDERS = ("gemini", "groq")


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in ("true", "1", "yes"):
        return True

    if normalized in ("false", "0", "no"):
        return False

    raise AIConfigurationError(
        f"{name} must be true or false."
    )


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default))

    try:
        number = int(value)
    except ValueError as exc:
        raise AIConfigurationError(
            f"{name} must be an integer."
        ) from exc

    if number < 0:
        raise AIConfigurationError(
            f"{name} cannot be negative."
        )

    return number


def build_ai_manager() -> AIManager:
    """Build an AI manager from trusted environment configuration."""

    if _get_bool("ALLOW_PAID_PROVIDERS", False):
        raise AIConfigurationError(
            "Paid AI providers are disabled for AutoResolve."
        )

    enabled = tuple(
        dict.fromkeys(
            value.strip().lower()
            for value in os.getenv(
                "AI_ENABLED_PROVIDERS",
                "gemini,groq",
            ).split(",")
            if value.strip()
        )
    )

    if not enabled:
        raise AIConfigurationError(
            "No AI providers are enabled."
        )

    unsupported = set(enabled) - set(SUPPORTED_PROVIDERS)

    if unsupported:
        raise AIConfigurationError(
            f"Unsupported providers: {sorted(unsupported)}"
        )

    primary = os.getenv(
        "AI_PRIMARY_PROVIDER",
        "gemini",
    ).strip().lower()

    router = ModelRouter(
        enabled_providers=enabled,
        default_provider=primary,
    )

    registry = ProviderRegistry()

    if "gemini" in enabled:
        registry.register(GeminiProvider())

    if "groq" in enabled:
        registry.register(GroqProvider())

    limits = {
        name: _get_int(
            f"AI_{name.upper()}_DAILY_LIMIT",
            20 if name == "gemini" else 30,
        )
        for name in enabled
    }

    database_path = Path(
        os.getenv(
            "AI_USAGE_DB_PATH",
            ".autoresolve_data/ai_usage.sqlite3",
        )
    )

    tracker = SQLiteUsageTracker(
        database_path=database_path,
        daily_limits=limits,
    )

    timeout_value = os.getenv(
        "AI_REQUEST_TIMEOUT",
        "60",
    )

    try:
        timeout = float(timeout_value)
    except ValueError as exc:
        raise AIConfigurationError(
            "AI_REQUEST_TIMEOUT must be numeric."
        ) from exc

    retries = _get_int("AI_MAX_RETRIES", 0)

    return AIManager(
        registry=registry,
        default_provider=primary,
        model_router=router,
        fallback_enabled=_get_bool(
            "AI_FALLBACK_ENABLED", False
        ),
        request_timeout=timeout,
        max_retries=retries,
        usage_tracker=tracker,
    )

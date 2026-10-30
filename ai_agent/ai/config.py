
"""Configuration for the provider-independent AI framework."""

import os
from dataclasses import dataclass

from .exceptions import AIConfigurationError


@dataclass(frozen=True)
class AISettings:
    primary_provider: str
    enabled_providers: tuple[str, ...]
    fallback_enabled: bool
    request_timeout: int
    allow_paid_providers: bool


def load_ai_settings() -> AISettings:
    """Read and validate AI settings from environment variables."""

    primary = os.getenv(
        "AI_PRIMARY_PROVIDER", "gemini"
    ).strip().lower()

    enabled = tuple(
        name.strip().lower()
        for name in os.getenv(
            "AI_ENABLED_PROVIDERS", "gemini"
        ).split(",")
        if name.strip()
    )

    fallback = os.getenv(
        "AI_FALLBACK_ENABLED", "false"
    ).strip().lower() == "true"

    allow_paid = os.getenv(
        "ALLOW_PAID_PROVIDERS", "false"
    ).strip().lower() == "true"

    try:
        timeout = int(
            os.getenv("AI_REQUEST_TIMEOUT", "60")
        )
    except ValueError as exc:
        raise AIConfigurationError(
            "AI_REQUEST_TIMEOUT must be an integer."
        ) from exc

    if timeout <= 0:
        raise AIConfigurationError(
            "AI_REQUEST_TIMEOUT must be positive."
        )

    if not enabled or primary not in enabled:
        raise AIConfigurationError(
            "Primary AI provider must be enabled."
        )

    if allow_paid:
        raise AIConfigurationError(
            "Paid AI providers are disabled for AutoResolve."
        )

    return AISettings(
        primary_provider=primary,
        enabled_providers=enabled,
        fallback_enabled=fallback,
        request_timeout=timeout,
        allow_paid_providers=False,
    )

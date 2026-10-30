
"""Track temporary AI provider unavailability."""

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic


@dataclass
class ProviderStatus:
    failures: int = 0
    cooldown_until: float = 0.0


class ProviderHealthTracker:
    """Maintain in-memory cooldowns for AI providers."""

    def __init__(
        self,
        cooldown_seconds: float = 60,
        clock: Callable[[], float] = monotonic,
    ):
        if cooldown_seconds < 0:
            raise ValueError(
                "Cooldown duration cannot be negative."
            )

        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self._status: dict[str, ProviderStatus] = {}

    def is_available(self, provider: str) -> bool:
        status = self._status.get(provider.lower())

        if status is None:
            return True

        return self.clock() >= status.cooldown_until

    def record_failure(self, provider: str) -> None:
        name = provider.lower()

        status = self._status.setdefault(
            name, ProviderStatus()
        )

        status.failures += 1
        status.cooldown_until = (
            self.clock() + self.cooldown_seconds
        )

    def record_success(self, provider: str) -> None:
        self._status[provider.lower()] = ProviderStatus()

    def remaining_cooldown(self, provider: str) -> float:
        status = self._status.get(provider.lower())

        if status is None:
            return 0.0

        return max(
            0.0,
            status.cooldown_until - self.clock(),
        )

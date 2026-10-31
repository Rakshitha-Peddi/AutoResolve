
"""Local daily request-budget tracking for AI providers."""

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock


class AIUsageLimitError(Exception):
    """Configured AI request budget has been exhausted."""


class AIUsageTracker:
    """Track the number of requests attempted per provider per UTC day."""

    def __init__(
        self,
        daily_limits: dict[str, int],
        clock: Callable[[], datetime] | None = None,
    ):
        self.daily_limits = {
            name.strip().lower(): limit
            for name, limit in daily_limits.items()
        }

        if not self.daily_limits:
            raise ValueError("At least one daily limit is required.")

        if any(
            not name
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 0
            for name, limit in self.daily_limits.items()
        ):
            raise ValueError(
                "Provider names must be nonempty and limits "
                "must be nonnegative integers."
            )

        self.clock = clock or (
            lambda: datetime.now(UTC)
        )
        self._counts: dict[tuple[str, str], int] = {}
        self._lock = Lock()

    def _current_day(self) -> str:
        now = self.clock()

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError(
                "Usage tracker clock must return a "
                "timezone-aware datetime."
            )

        return now.astimezone(UTC).date().isoformat()

    def reserve_request(self, provider: str) -> None:
        """Atomically count one request attempt before sending it."""
        name = provider.strip().lower()

        with self._lock:
            if name not in self.daily_limits:
                raise AIUsageLimitError(
                    f"No request budget configured for '{name}'."
                )

            day = self._current_day()
            key = (day, name)
            used = self._counts.get(key, 0)
            limit = self.daily_limits[name]

            if used >= limit:
                raise AIUsageLimitError(
                    f"Daily request budget exhausted for '{name}': "
                    f"{used}/{limit}."
                )

            self._counts[key] = used + 1

    def get_usage(self, provider: str) -> dict[str, int]:
        """Get today's usage for a configured provider."""
        name = provider.strip().lower()

        with self._lock:
            if name not in self.daily_limits:
                raise AIUsageLimitError(
                    f"No request budget configured for '{name}'."
                )

            used = self._counts.get(
                (self._current_day(), name), 0
            )
            limit = self.daily_limits[name]

            return {
                "used": used,
                "limit": limit,
                "remaining": max(0, limit - used),
            }

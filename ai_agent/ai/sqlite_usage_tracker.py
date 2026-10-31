
"""SQLite-backed daily AI request budgets."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from .usage_tracker import AIUsageLimitError


class SQLiteUsageTracker:
    """Persist daily request counts across process restarts."""

    def __init__(
        self,
        database_path: str | Path,
        daily_limits: dict[str, int],
        clock: Callable[[], datetime] | None = None,
    ):
        self.database_path = Path(database_path)
        self.daily_limits = {
            name.strip().lower(): limit
            for name, limit in daily_limits.items()
        }

        if (
            not self.daily_limits
            or any(
                not name
                or type(limit) is not int
                or limit < 0
                for name, limit in self.daily_limits.items()
            )
        ):
            raise ValueError("Invalid provider daily limits.")

        self.clock = clock or (lambda: datetime.now(UTC))

        self.database_path.parent.mkdir(
            parents=True, exist_ok=True
        )

        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                    CREATE TABLE IF NOT EXISTS ai_daily_usage (
                        day TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        requests INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (day, provider)
                    )
                    """
            )

    def _connect(self):
        return sqlite3.connect(
            self.database_path,
            timeout=10,
        )

    def _current_day(self) -> str:
        now = self.clock()

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError(
                "Clock must return a timezone-aware datetime."
            )

        return now.astimezone(UTC).date().isoformat()

    def reserve_request(self, provider: str) -> None:
        """Atomically reserve one request before contacting the API."""
        name = provider.strip().lower()

        if name not in self.daily_limits:
            raise AIUsageLimitError(
                f"No request budget configured for '{name}'."
            )

        day = self._current_day()
        limit = self.daily_limits[name]

        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute(
                """
                    SELECT requests
                    FROM ai_daily_usage
                    WHERE day = ? AND provider = ?
                    """,
                (day, name),
            ).fetchone()

            used = row[0] if row else 0

            if used >= limit:
                raise AIUsageLimitError(
                    f"Daily request budget exhausted "
                    f"for '{name}': {used}/{limit}."
                )

            conn.execute(
                """
                    INSERT INTO ai_daily_usage
                        (day, provider, requests)
                    VALUES (?, ?, 1)
                    ON CONFLICT(day, provider)
                    DO UPDATE SET
                        requests = requests + 1
                    """,
                (day, name),
            )

    def get_usage(self, provider: str) -> dict[str, int]:
        """Read today's persisted usage."""
        name = provider.strip().lower()

        if name not in self.daily_limits:
            raise AIUsageLimitError(
                f"No request budget configured for '{name}'."
            )

        day = self._current_day()

        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT requests
                FROM ai_daily_usage
                WHERE day = ? AND provider = ?
                """,
                (day, name),
            ).fetchone()

        used = row[0] if row else 0
        limit = self.daily_limits[name]

        return {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
        }

"""The Bug table. One row holds a bug's whole lifecycle."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base

# The four statuses a bug moves through.
FIXING = "fixing"                    # the AI agent is working on it
AWAITING_REVIEW = "awaiting_review"  # a fix is ready for the developer
MERGED = "merged"                    # approved and merged
FAILED = "failed"                    # iteration limit reached, or the AI hit an error
STATUSES = (FIXING, AWAITING_REVIEW, MERGED, FAILED)


def utcnow() -> datetime:
    """Naive UTC, which is what SQLite round-trips cleanly."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Bug(Base):
    __tablename__ = "bugs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    repo: Mapped[str] = mapped_column(String(500))
    reporter: Mapped[str] = mapped_column(String(200), default="unknown")
    status: Mapped[str] = mapped_column(String(20), default=FIXING, index=True)

    # Number of AI attempts started so far (1 = the first attempt).
    iteration: Mapped[int] = mapped_column(Integer, default=1)

    # The latest attempt, denormalised so the review panel needs no joins.
    root_cause: Mapped[str] = mapped_column(Text, default="")
    changed_files: Mapped[list] = mapped_column(JSON, default=list)  # [{"path", "diff"}]
    test_results: Mapped[dict] = mapped_column(JSON, default=dict)
    branch: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # Every attempt, newest last, so earlier fixes stay visible after a retry.
    attempts: Mapped[list] = mapped_column(JSON, default=list)
    # Timeline of what happened: [{"at", "event", "iteration", "message"}]
    history: Mapped[list] = mapped_column(JSON, default=list)
    # Developer change requests: [{"iteration", "text", "at"}]
    feedback: Mapped[list] = mapped_column(JSON, default=list)

    # Where the bug came from ("api" or "sheet"). source_ref is unique, so a
    # sheet row can never be imported twice.
    source: Mapped[str] = mapped_column(String(20), default="api")
    source_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    @property
    def public_id(self) -> str:
        return f"BUG-{self.id}"

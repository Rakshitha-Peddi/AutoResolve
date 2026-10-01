"""Shapes of the data going in and out of the API."""
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator

from backend.config import MAX_ITERATIONS

Status = Literal["fixing", "awaiting_review", "merged", "failed"]


def iso(dt: Optional[datetime]) -> Optional[str]:
    """Stored datetimes are naive UTC; send them out as explicit UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


# ---------- requests ----------

class BugCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    # "repository" is accepted too, so either spelling works from a client.
    repo: str = Field(min_length=1, max_length=500,
                      validation_alias=AliasChoices("repo", "repository"))
    reporter: str = Field(default="unknown", max_length=200)

    @field_validator("title", "description", "repo", "reporter")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class FeedbackCreate(BaseModel):
    feedback: str = Field(min_length=1, validation_alias=AliasChoices("feedback", "text", "message"))

    @field_validator("feedback")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("feedback must not be blank")
        return v


# ---------- responses ----------

class BugSummary(BaseModel):
    """One row in the bug queue."""
    id: str
    title: str
    repo: str
    reporter: str
    status: Status
    iteration: int
    max_iterations: int
    created_at: str
    updated_at: str

    @classmethod
    def from_bug(cls, b: Any) -> "BugSummary":
        return cls(
            id=b.public_id, title=b.title, repo=b.repo, reporter=b.reporter,
            status=b.status, iteration=b.iteration, max_iterations=MAX_ITERATIONS,
            created_at=iso(b.created_at), updated_at=iso(b.updated_at),
        )


class BugDetail(BugSummary):
    """Everything the review panel shows."""
    description: str
    source: str
    root_cause: str
    changed_files: list[dict]
    test_results: dict
    branch: Optional[str]
    attempts: list[dict]
    history: list[dict]
    feedback: list[dict]
    resolved_at: Optional[str]

    @classmethod
    def from_bug(cls, b: Any) -> "BugDetail":
        return cls(
            **BugSummary.from_bug(b).model_dump(),
            description=b.description, source=b.source,
            root_cause=b.root_cause or "",
            changed_files=list(b.changed_files or []),
            test_results=dict(b.test_results or {}),
            branch=b.branch,
            attempts=list(b.attempts or []),
            history=list(b.history or []),
            feedback=list(b.feedback or []),
            resolved_at=iso(b.resolved_at),
        )


class Metrics(BaseModel):
    """Rates are fractions between 0 and 1."""
    total: int
    fixing: int
    awaiting_review: int
    merged: int
    failed: int
    resolution_rate: float       # merged / all bugs
    first_attempt_rate: float    # merged on attempt 1 / merged
    avg_iterations: float        # average AI attempts per bug
    approval_rate: float         # approvals / (approvals + change requests)
    approvals: int
    change_requests: int

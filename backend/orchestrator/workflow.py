"""Bug lifecycle orchestration for AutoResolve.

workflow.py talks only to FixEngine. The engine owns AI analysis, patch
generation, validation and merge mechanics.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import MAX_ITERATIONS
from backend.database.session import SessionLocal
from backend.models.bug import (
    AWAITING_REVIEW,
    FAILED,
    FIXING,
    MERGED,
    Bug,
)
from backend.models.schemas import BugCreate, Metrics
from backend.orchestrator.engine import FixRequest, get_engine


class BugNotFound(Exception):
    """Requested bug does not exist."""


class InvalidState(Exception):
    """Requested operation is invalid for the bug's current state."""


class MergeFailed(Exception):
    """Approved change could not be merged."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _add_history(
    bug: Bug,
    event: str,
    message: str = "",
) -> None:
    history = list(bug.history or [])
    history.append(
        {
            "at": _utcnow().isoformat() + "Z",
            "event": event,
            "iteration": bug.iteration,
            "message": message,
        }
    )
    bug.history = history
    # SQLite timestamp resolution can otherwise leave two rapid updates equal.
    bug.updated_at = _utcnow()


def _get_bug(db: Session, bug_id: str | int) -> Bug:
    if isinstance(bug_id, str):
        value = bug_id.strip()

        if value.upper().startswith("BUG-"):
            value = value[4:]

        try:
            numeric_id = int(value)
        except ValueError as exc:
            raise BugNotFound(f"Bug '{bug_id}' was not found.") from exc
    else:
        numeric_id = int(bug_id)

    bug = db.get(Bug, numeric_id)

    if bug is None:
        raise BugNotFound(f"Bug '{bug_id}' was not found.")

    return bug


def get_bug(db: Session, bug_id: str | int) -> Bug:
    return _get_bug(db, bug_id)


def create_bug(
    db: Session,
    data: BugCreate,
    source: str = "api",
    source_ref: str | None = None,
) -> Bug:
    bug = Bug(
        title=data.title,
        description=data.description,
        repo=data.repo,
        reporter=data.reporter,
        status=FIXING,
        iteration=0,
        source=source,
        source_ref=source_ref,
        attempts=[],
        history=[],
        feedback=[],
        changed_files=[],
        test_results={},
    )

    db.add(bug)
    db.commit()
    db.refresh(bug)

    _add_history(
        bug,
        "reported",
        f"Bug reported by {data.reporter}.",
    )

    db.commit()
    db.refresh(bug)

    return bug


def _make_request(bug: Bug) -> FixRequest:
    return FixRequest(
        bug_id=bug.public_id,
        title=bug.title,
        description=bug.description,
        repo=bug.repo,
        iteration=bug.iteration,
        feedback=[
            item["text"]
            for item in (bug.feedback or [])
            if item.get("text")
        ],
    )


def run_iteration(bug_id: int) -> Bug:
    """Run one AI repair attempt in its own database session."""

    with SessionLocal() as db:
        bug = _get_bug(db, bug_id)

        # Once a candidate is ready, running the background task again must
        # not silently create another attempt.
        if bug.status != FIXING:
            return bug

        if bug.iteration >= MAX_ITERATIONS:
            bug.status = FAILED
            _add_history(
                bug,
                "failed",
                f"Maximum iterations ({MAX_ITERATIONS}) reached.",
            )
            db.commit()
            db.refresh(bug)
            return bug

        bug.iteration += 1
        bug.status = FIXING
        bug.updated_at = _utcnow()

        db.commit()
        db.refresh(bug)

        engine = get_engine()
        request = _make_request(bug)

        try:
            result = engine.propose_fix(request)

            bug.root_cause = result.root_cause
            bug.changed_files = result.changed_files
            bug.test_results = result.test_results
            bug.branch = result.branch

            attempt = {
                "iteration": bug.iteration,
                "summary": result.summary,
                "plan": result.plan,
                "changed_files": result.changed_files,
                "test_results": result.test_results,
                "branch": result.branch,
                "outcome": "pending_review",
            }

            attempts = [dict(item) for item in (bug.attempts or [])]
            attempts.append(attempt)
            bug.attempts = attempts

            if result.test_results.get("passed") is not True:
                bug.status = FAILED

                _add_history(
                    bug,
                    "failed",
                    "Generated fix did not pass validation.",
                )
            else:
                bug.status = AWAITING_REVIEW

                _add_history(
                    bug,
                    "fix_proposed",
                    result.summary,
                )

            db.commit()
            db.refresh(bug)

            return bug

        except Exception as exc:
            bug.status = FAILED

            _add_history(
                bug,
                "failed",
                str(exc),
            )

            db.commit()
            db.refresh(bug)

            return bug


def approve(db: Session, bug: Bug) -> Bug:
    if bug.status != AWAITING_REVIEW:
        raise InvalidState(
            f"Bug {bug.public_id} is not awaiting review."
        )

    attempts = [dict(item) for item in (bug.attempts or [])]

    if not attempts:
        raise InvalidState(
            f"Bug {bug.public_id} has no repair attempt to approve."
        )

    latest = attempts[-1]
    engine = get_engine()

    try:
        merge_ref = engine.merge(
            bug.repo,
            bug.branch,
        )

    except Exception as exc:
        # A merge failure must NOT destroy a valid review candidate.
        _add_history(
            bug,
            "merge_failed",
            str(exc),
        )

        db.commit()
        db.refresh(bug)

        raise MergeFailed(str(exc)) from exc

    latest["outcome"] = "approved"

    attempts[-1] = latest
    bug.attempts = attempts

    bug.status = MERGED
    bug.resolved_at = _utcnow()

    _add_history(
        bug,
        "merged",
        merge_ref or "Change merged.",
    )

    # Notification is represented in the lifecycle history for now. The
    # notification service can be plugged into this point later.
    _add_history(
        bug,
        "tester_notified",
        "Tester notified of successful resolution.",
    )

    db.commit()
    db.refresh(bug)

    return bug


def request_changes(
    db: Session,
    bug: Bug,
    feedback: str,
) -> Bug:
    if bug.status != AWAITING_REVIEW:
        raise InvalidState(
            f"Bug {bug.public_id} is not awaiting review."
        )

    feedback = feedback.strip()

    if not feedback:
        raise ValueError("Feedback cannot be blank.")

    attempts = [dict(item) for item in (bug.attempts or [])]

    if attempts:
        attempts[-1]["outcome"] = "changes_requested"
        bug.attempts = attempts

    feedback_items = list(bug.feedback or [])

    feedback_items.append(
        {
            "iteration": bug.iteration,
            "text": feedback,
            "at": _utcnow().isoformat() + "Z",
        }
    )

    bug.feedback = feedback_items

    if bug.iteration >= MAX_ITERATIONS:
        bug.status = FAILED

        _add_history(
            bug,
            "failed",
            f"Maximum iterations ({MAX_ITERATIONS}) reached.",
        )

        db.commit()
        db.refresh(bug)

        return bug

    bug.status = FIXING

    _add_history(
        bug,
        "changes_requested",
        feedback,
    )

    db.commit()
    db.refresh(bug)

    return bug


def compute_metrics(db: Session) -> Metrics:
    bugs = list(
        db.scalars(
            select(Bug)
        )
    )

    total = len(bugs)

    fixing = sum(
        bug.status == FIXING
        for bug in bugs
    )

    awaiting_review = sum(
        bug.status == AWAITING_REVIEW
        for bug in bugs
    )

    merged = sum(
        bug.status == MERGED
        for bug in bugs
    )

    failed = sum(
        bug.status == FAILED
        for bug in bugs
    )

    resolution_rate = (
        merged / total
        if total
        else 0
    )

    merged_bugs = [
        bug
        for bug in bugs
        if bug.status == MERGED
    ]

    first_attempt_rate = (
        sum(
            bug.iteration == 1
            for bug in merged_bugs
        ) / len(merged_bugs)
        if merged_bugs
        else 0
    )

    avg_iterations = (
        sum(bug.iteration for bug in bugs) / total
        if total
        else 0
    )

    approvals = sum(
        1
        for bug in bugs
        for attempt in (bug.attempts or [])
        if attempt.get("outcome") == "approved"
    )

    change_requests = sum(
        1
        for bug in bugs
        for attempt in (bug.attempts or [])
        if attempt.get("outcome") == "changes_requested"
    )

    approval_rate = (
        approvals / (approvals + change_requests)
        if approvals + change_requests
        else 0
    )

    return Metrics(
        total=total,
        fixing=fixing,
        awaiting_review=awaiting_review,
        merged=merged,
        failed=failed,
        resolution_rate=resolution_rate,
        first_attempt_rate=first_attempt_rate,
        avg_iterations=avg_iterations,
        approval_rate=approval_rate,
        approvals=approvals,
        change_requests=change_requests,
    )


class AutoResolveWorkflow:
    """Compatibility wrapper used by the component-level integration tests."""

    def __init__(
        self,
        github_client,
        ai_engine,
        workspace_manager,
        patch_applier,
        test_runner,
    ):
        self.github_client = github_client
        self.ai_engine = ai_engine
        self.workspace_manager = workspace_manager
        self.patch_applier = patch_applier
        self.test_runner = test_runner

    def analyze_bug(
        self,
        repo_url: str,
        bug_name: str,
        bug_description: str,
        relevant_files: list[str],
    ) -> dict:
        repository_files = []

        for path in relevant_files:
            repository_files.append(
                {
                    "path": path,
                    "content": self.github_client.get_file(
                        repo_url,
                        path,
                    ),
                }
            )

        analysis = self.ai_engine.analyze_bug(
            bug_name=bug_name,
            bug_description=bug_description,
            repository_files=repository_files,
        )

        return {
            "bug_name": bug_name,
            "bug_description": bug_description,
            "analysis": analysis,
        }

    def apply_and_verify(
        self,
        repo_url: str,
        patch: str,
        branch: str = "main",
    ) -> dict:
        workspace = self.workspace_manager.create_workspace(
            repo_url,
            branch=branch,
        )

        try:
            self.patch_applier.apply_patch(
                workspace,
                patch,
            )

            test_result = self.test_runner.run(workspace)

            return {
                "success": test_result["success"],
                "workspace": str(workspace),
                "test_result": test_result,
            }

        finally:
            self.workspace_manager.cleanup(workspace)
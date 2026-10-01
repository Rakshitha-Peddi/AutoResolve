"""HTTP endpoints. Each one validates the request and hands off to workflow.py."""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.models.bug import FIXING, STATUSES, Bug
from backend.models.schemas import BugCreate, BugDetail, BugSummary, FeedbackCreate, Metrics
from backend.orchestrator import sheets, workflow

router = APIRouter(prefix="/api")


def register_error_handlers(app: FastAPI) -> None:
    """Turn workflow errors into clean HTTP responses."""
    def handler(status_code: int):
        async def _handle(_: Request, exc: Exception):
            return JSONResponse(status_code=status_code, content={"detail": str(exc)})
        return _handle

    app.add_exception_handler(workflow.BugNotFound, handler(404))
    app.add_exception_handler(workflow.InvalidState, handler(409))
    app.add_exception_handler(workflow.MergeFailed, handler(502))
    app.add_exception_handler(sheets.SheetsError, handler(502))


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/metrics", response_model=Metrics)
def metrics(db: Session = Depends(get_db)):
    return workflow.compute_metrics(db)


@router.get("/bugs", response_model=list[BugSummary])
def list_bugs(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = select(Bug).order_by(Bug.updated_at.desc(), Bug.id.desc())
    if status is not None:
        if status not in STATUSES:
            raise HTTPException(422, f"status must be one of: {', '.join(STATUSES)}")
        query = query.where(Bug.status == status)
    return [BugSummary.from_bug(b) for b in db.scalars(query)]


@router.post("/bugs", response_model=BugDetail, status_code=201)
def report_bug(data: BugCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    bug = workflow.create_bug(db, data)
    background.add_task(workflow.run_iteration, bug.id)
    return BugDetail.from_bug(bug)


@router.get("/bugs/{bug_id}", response_model=BugDetail)
def get_bug(bug_id: str, db: Session = Depends(get_db)):
    return BugDetail.from_bug(workflow.get_bug(db, bug_id))


@router.post("/bugs/{bug_id}/approve", response_model=BugDetail)
def approve(bug_id: str, db: Session = Depends(get_db)):
    bug = workflow.get_bug(db, bug_id)
    return BugDetail.from_bug(workflow.approve(db, bug))


@router.post("/bugs/{bug_id}/feedback", response_model=BugDetail)
def send_feedback(bug_id: str, data: FeedbackCreate, background: BackgroundTasks,
                  db: Session = Depends(get_db)):
    bug = workflow.get_bug(db, bug_id)
    workflow.request_changes(db, bug, data.feedback)
    if bug.status == FIXING:  # attempts remain: try again in the background
        background.add_task(workflow.run_iteration, bug.id)
    return BugDetail.from_bug(bug)


@router.post("/sheets/sync")
def sync_sheets(background: BackgroundTasks):
    if not sheets.is_enabled():
        raise HTTPException(400, "Google Sheets intake is off. Set GOOGLE_SHEET_ID and restart.")
    new_ids = sheets.sync_sheet()
    for bug_id in new_ids:
        background.add_task(workflow.run_iteration, bug_id)
    return {"created": [f"BUG-{i}" for i in new_ids], "count": len(new_ids)}

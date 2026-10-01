import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database.session import get_db
from backend.models.bug import Bug
from backend.models.schemas import BugCreate, FeedbackCreate
from backend.orchestrator.workflow import Workflow

router = APIRouter(prefix="/api")

def out(b):
    return {
        "id": b.id, "title": b.title, "description": b.description, "repository": b.repository,
        "reporter": b.reporter, "status": b.status, "current_iteration": b.current_iteration,
        "root_cause": b.root_cause or "", "relevant_files": json.loads(b.relevant_files or "[]"),
        "created_at": b.created_at.isoformat(), "updated_at": b.updated_at.isoformat(),
        "resolved_at": b.resolved_at.isoformat() if b.resolved_at else None,
    }

@router.get("/health")
def health(): return {"status": "ok"}

@router.post("/bugs")
def create(data: BugCreate, db: Session = Depends(get_db)):
    return out(Workflow(db).create_bug(data))

@router.get("/bugs")
def list_bugs(db: Session = Depends(get_db)):
    return [out(x) for x in db.query(Bug).order_by(Bug.id.desc()).all()]

@router.get("/bugs/{bug_id}")
def get_bug(bug_id: int, db: Session = Depends(get_db)):
    b = db.get(Bug, bug_id)
    if not b: raise HTTPException(404, "Bug not found")
    data = out(b)
    data["iterations"] = [{"number": i.iteration_number, "analysis": json.loads(i.analysis or "{}"), "plan": json.loads(i.repair_plan or "[]"), "patch": i.patch, "tests": json.loads(i.tests or "{}"), "validation": json.loads(i.validation or "{}"), "status": i.status} for i in b.iterations]
    data["feedback"] = [{"developer": f.developer, "feedback": f.feedback, "created_at": f.created_at.isoformat()} for f in b.feedback]
    data["history"] = [{"event": e.event_type, "message": e.message, "metadata": json.loads(e.metadata_json or "{}"), "timestamp": e.timestamp.isoformat()} for e in b.events]
    return data

@router.post("/bugs/{bug_id}/analyze")
def analyze(bug_id: int, db: Session = Depends(get_db)):
    b = db.get(Bug, bug_id)
    if not b: raise HTTPException(404, "Bug not found")
    if b.current_iteration: raise HTTPException(400, "An iteration already exists; use fix/revision")
    it = Workflow(db).run_iteration(b)
    return {"ok": bool(it), "status": b.status}

@router.post("/bugs/{bug_id}/fix")
def fix(bug_id: int, db: Session = Depends(get_db)):
    b = db.get(Bug, bug_id)
    if not b: raise HTTPException(404, "Bug not found")
    if b.status not in ("NEW", "FIXING", "FAILED"): raise HTTPException(400, f"Cannot fix from {b.status}")
    it = Workflow(db).run_iteration(b)
    return {"ok": bool(it), "status": b.status}

@router.post("/bugs/{bug_id}/feedback")
def feedback(bug_id: int, data: FeedbackCreate, db: Session = Depends(get_db)):
    b = db.get(Bug, bug_id)
    if not b: raise HTTPException(404, "Bug not found")
    try: Workflow(db).request_feedback(b, data.feedback, data.developer)
    except ValueError as e: raise HTTPException(400, str(e))
    return {"ok": True, "status": b.status}

@router.post("/bugs/{bug_id}/approve")
def approve(bug_id: int, db: Session = Depends(get_db)):
    b = db.get(Bug, bug_id)
    if not b: raise HTTPException(404, "Bug not found")
    try: pr = Workflow(db).approve(b)
    except ValueError as e: raise HTTPException(400, str(e))
    return {"ok": True, "status": b.status, "pull_request": pr}

@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    bugs = db.query(Bug).all()
    merged = [b for b in bugs if b.status == "MERGED"]
    approvals = len([e for b in bugs for e in b.events if e.event_type == "MERGED"])
    feedbacks = len([f for b in bugs for f in b.feedback])
    return {"total": len(bugs), "resolved": len(merged), "resolution_rate": (len(merged)/len(bugs) if bugs else 0), "first_attempt_fix_rate": (sum(b.current_iteration == 1 for b in merged)/len(merged) if merged else 0), "avg_iterations": (sum(b.current_iteration for b in bugs)/len(bugs) if bugs else 0), "approval_events": approvals, "change_requests": feedbacks}

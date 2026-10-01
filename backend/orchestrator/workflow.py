import json
from datetime import datetime
from pathlib import Path
from backend.models.bug import Bug, Iteration, Feedback, AuditEvent
from backend.config import MAX_ITERATIONS, PROJECT_ROOT, EXECUTION_TIMEOUT_SECONDS
from ai_agent.engine import CodeFixEngine
from execution.workspace import WorkspaceManager
from execution.patch_applier import PatchApplier
from execution.test_runner import TestRunner
from execution.git_manager import GitManager
from review.notifications import NotificationService

class Workflow:
    def __init__(self, db):
        self.db = db
        self.engine = CodeFixEngine()
        self.workspace = WorkspaceManager()
        self.applier = PatchApplier()
        self.runner = TestRunner()
        self.git = GitManager()
        self.notify = NotificationService()

    def event(self, bug, kind, message="", metadata=None):
        self.db.add(AuditEvent(bug_id=bug.id, event_type=kind, message=message, metadata_json=json.dumps(metadata or {})))
        self.db.commit()

    def create_bug(self, data):
        bug = Bug(title=data.title, description=data.description, repository=data.repository, reporter=data.reporter, status="NEW")
        self.db.add(bug); self.db.commit(); self.db.refresh(bug)
        self.event(bug, "BUG_CREATED", bug.title)
        return bug

    def repo_path(self, bug):
        p = Path(bug.repository)
        return p if p.is_absolute() else Path(PROJECT_ROOT) / p

    def run_iteration(self, bug):
        if bug.current_iteration >= MAX_ITERATIONS:
            bug.status = "FAILED"; self.db.commit(); return
        bug.current_iteration += 1
        bug.status = "ANALYZING"; self.db.commit(); self.event(bug, "ANALYSIS_STARTED")
        feedback = "\n".join(x.feedback for x in bug.feedback)
        repo = self.repo_path(bug)
        proposal = self.engine.propose_fix(bug, str(repo), feedback)
        analysis = proposal["analysis"]
        bug.root_cause = analysis["root_cause"]
        bug.relevant_files = json.dumps(analysis["relevant_files"])
        it = Iteration(bug_id=bug.id, iteration_number=bug.current_iteration, analysis=json.dumps(analysis), repair_plan=json.dumps(proposal["plan"]), patch=proposal["patch"], tests=json.dumps(proposal["tests"]), status="PATCH_GENERATED")
        self.db.add(it); self.db.commit(); self.db.refresh(it)
        bug.status = "TESTING"; self.db.commit(); self.event(bug, "PATCH_GENERATED", metadata={"iteration": it.iteration_number})
        root, work = self.workspace.create(repo)
        try:
            self.applier.apply(work, proposal["patch"])
            # Add the generated regression test to the isolated candidate workspace.
            regression = Path(work) / "tests" / "test_autoresolve_regression.py"
            regression.write_text("""from src.user_service import get_user_name


def test_missing_user_is_handled():
    assert get_user_name(None) is None
""")
            validation = self.runner.run(work, EXECUTION_TIMEOUT_SECONDS)
        except Exception as e:
            validation = {"passed": False, "error": str(e)}
        finally:
            self.workspace.destroy(root)
        it.validation = json.dumps(validation)
        it.status = "PASSED" if validation.get("passed") else "FAILED"
        if validation.get("passed"):
            bug.status = "AWAITING_REVIEW"
            self.event(bug, "VALIDATION_PASSED", metadata={"iteration": it.iteration_number})
        else:
            bug.status = "FAILED" if bug.current_iteration >= MAX_ITERATIONS else "FIXING"
            self.event(bug, "VALIDATION_FAILED", metadata={"iteration": it.iteration_number, "validation": validation})
        self.db.commit()
        return it

    def approve(self, bug):
        if bug.status != "AWAITING_REVIEW": raise ValueError("Bug is not awaiting review")
        repo = self.repo_path(bug)
        latest = max(bug.iterations, key=lambda x: x.iteration_number)
        # Apply the approved patch to the real repository, then commit on a dedicated branch.
        self.applier.apply(repo, latest.patch)
        pr = self.git.create_branch_commit(repo, bug.id, latest.patch)
        bug.status = "MERGED"; bug.resolved_at = datetime.utcnow(); self.db.commit()
        self.event(bug, "MERGED", metadata=pr)
        msg = self.notify.notify_tester(bug)
        self.event(bug, "TESTER_NOTIFIED", msg)
        return pr

    def request_feedback(self, bug, feedback, developer):
        if bug.status != "AWAITING_REVIEW": raise ValueError("Bug is not awaiting review")
        latest = max(bug.iterations, key=lambda x: x.iteration_number)
        self.db.add(Feedback(bug_id=bug.id, iteration_id=latest.id, developer=developer, feedback=feedback))
        bug.status = "FIXING"; self.db.commit(); self.event(bug, "DEVELOPER_FEEDBACK", feedback)
        if bug.current_iteration >= MAX_ITERATIONS:
            bug.status = "FAILED"; self.db.commit(); return None
        return self.run_iteration(bug)

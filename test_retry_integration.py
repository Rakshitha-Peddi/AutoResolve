
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.session import Base
from backend.models.bug import Bug, FIXING, AWAITING_REVIEW
from backend.orchestrator import workflow


with tempfile.TemporaryDirectory() as temp_dir:
    db_path = Path(temp_dir) / "retry_test.db"
    test_engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    TestSession = sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=test_engine)

    with TestSession() as db:
        bug = Bug(
            title="get_user_name crashes on None",
            description="get_user_name crashes when user is None",
            repo="Albert-2106/autoresolve-practice",
            reporter="Test User",
            status=FIXING,
            iteration=0,
            source="manual",
            attempts=[],
            history=[],
            feedback=[],
            changed_files=[],
            test_results={},
        )
        db.add(bug)
        db.commit()
        bug_id = bug.id

    received_requests = []

    class FakeEngine:
        def propose_fix(self, request):
            received_requests.append(request)

            passed = len(received_requests) == 2

            return SimpleNamespace(
                root_cause="Missing None handling",
                summary="Mock repair attempt",
                plan=[],
                changed_files=[],
                test_results={
                    "passed": passed,
                    "stage": "tests",
                    "error": None if passed else "Mock test failure",
                    "stdout": "" if passed else "AssertionError",
                    "stderr": "",
                },
                branch="autoresolve/bug-1",
            )

    with (
        patch.object(workflow, "SessionLocal", TestSession),
        patch.object(workflow, "get_engine", return_value=FakeEngine()),
    ):
        result = workflow.run_iteration(bug_id)

    with TestSession() as db:
        saved_bug = db.get(Bug, bug_id)

        print("Final status:", saved_bug.status)
        print("Iterations:", saved_bug.iteration)
        print("Attempts recorded:", len(saved_bug.attempts))
        print("Feedback entries:", len(saved_bug.feedback))
        print(
            "Second attempt received feedback:",
            bool(received_requests[1].feedback),
        )

        assert saved_bug.status == AWAITING_REVIEW
        assert saved_bug.iteration == 2
        assert len(saved_bug.attempts) == 2
        assert len(saved_bug.feedback) == 1
        assert received_requests[1].feedback
        assert saved_bug.attempts[0]["outcome"] == "validation_failed"
        assert saved_bug.attempts[1]["outcome"] == "pending_review"

    test_engine.dispose()

print("Integration test PASSED")

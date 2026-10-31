
"""Database-backed tests for the current repair retry workflow."""

from unittest.mock import Mock

from backend.database.session import SessionLocal
from backend.models.bug import AWAITING_REVIEW, FAILED
from backend.models.schemas import BugCreate
from backend.orchestrator import workflow
from backend.orchestrator.engine import FixResult, StubEngine, set_engine


def make_result(passed, stage="tests"):
    if passed:
        test_results = {
            "passed": True,
            "stage": "tests",
            "exit_code": 0,
            "stdout": "1 passed",
            "stderr": "",
        }
    elif stage == "tests":
        test_results = {
            "passed": False,
            "stage": "tests",
            "exit_code": 1,
            "stdout": (
                "FAILED tests/test_regression.py::test_missing_user\n"
                "AssertionError: assert None == 'Guest'\n"
                "1 failed in 0.10s"
            ),
            "stderr": "",
        }
    else:
        test_results = {
            "passed": False,
            "stage": stage,
            "error": "Docker worker unavailable",
            "stdout": "",
            "stderr": "",
        }

    return FixResult(
        root_cause="Missing None handling",
        summary="Proposed missing-user fix",
        plan=["Handle None correctly"],
        changed_files=[{"path": "app.py", "diff": "example patch"}],
        test_results=test_results,
        branch=None,
    )


def create_test_bug():
    with SessionLocal() as db:
        bug = workflow.create_bug(
            db,
            BugCreate(
                title="Missing username",
                description="Return Guest when user is None",
                repo="example/test-repo",
                reporter="test-runner",
            ),
        )
        return bug.id


def run_with_fake_engine(fake_engine, bug_id):
    set_engine(fake_engine)
    try:
        return workflow.run_iteration(bug_id)
    finally:
        set_engine(StubEngine())


def test_failed_assertion_retries_and_then_succeeds(client):
    bug_id = create_test_bug()

    fake_engine = Mock()
    fake_engine.propose_fix.side_effect = [
        make_result(False),
        make_result(True),
    ]

    bug = run_with_fake_engine(fake_engine, bug_id)

    assert bug.status == AWAITING_REVIEW
    assert bug.iteration == 2
    assert fake_engine.propose_fix.call_count == 2

    assert len(bug.attempts) == 2
    assert bug.attempts[0]["outcome"] == "validation_failed"
    assert bug.attempts[1]["outcome"] == "pending_review"

    second_request = fake_engine.propose_fix.call_args_list[1].args[0]

    assert second_request.iteration == 2
    assert any(
        "None == 'Guest'" in item
        for item in second_request.feedback
    )

    events = [item["event"] for item in bug.history]
    assert "retry_pending" in events
    assert "fix_proposed" in events

    fake_engine.merge.assert_not_called()


def test_docker_failure_does_not_retry(client):
    bug_id = create_test_bug()

    fake_engine = Mock()
    fake_engine.propose_fix.return_value = make_result(
        False,
        stage="docker",
    )

    bug = run_with_fake_engine(fake_engine, bug_id)

    assert bug.status == FAILED
    assert bug.iteration == 1
    assert len(bug.attempts) == 1
    assert fake_engine.propose_fix.call_count == 1
    assert not any(
        item["event"] == "retry_pending"
        for item in bug.history
    )


def test_failed_assertions_stop_at_iteration_limit(client):
    bug_id = create_test_bug()

    fake_engine = Mock()
    fake_engine.propose_fix.return_value = make_result(False)

    bug = run_with_fake_engine(fake_engine, bug_id)

    # tests/conftest.py configures MAX_ITERATIONS=3.
    assert bug.status == FAILED
    assert bug.iteration == 3
    assert len(bug.attempts) == 3
    assert fake_engine.propose_fix.call_count == 3
    assert bug.history[-1]["event"] == "failed"

    fake_engine.merge.assert_not_called()

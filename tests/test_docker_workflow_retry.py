
"""Verify workflow retries using real Docker validation."""

import difflib
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock

from backend.database.session import SessionLocal
from backend.models.bug import AWAITING_REVIEW
from backend.models.schemas import BugCreate
from backend.orchestrator import workflow
from backend.orchestrator.engine import FixResult, StubEngine, set_engine
from backend.orchestrator.real_engine import RealFixEngine

ORIGINAL = (
    "def get_username(user):\n"
    '    return user["name"]\n'
)

WRONG_FIX = (
    "def get_username(user):\n"
    '    return user["name"] if user is not None else None\n'
)

CORRECT_FIX = (
    "def get_username(user):\n"
    "    if user is None:\n"
    '        return "Guest"\n'
    '    return user["name"]\n'
)

REGRESSION = (
    "from app import get_username\n\n"
    "def test_none_user():\n"
    '    assert get_username(None) == "Guest"\n'
)


def make_patch(corrected):
    diff = "".join(
        difflib.unified_diff(
            ORIGINAL.splitlines(keepends=True),
            corrected.splitlines(keepends=True),
            fromfile="a/app.py",
            tofile="b/app.py",
        )
    )
    return "diff --git a/app.py b/app.py\n" + diff


def test_docker_failure_then_successful_retry(client):
    project_root = Path(__file__).resolve().parents[1]
    workspace = project_root / ".autoresolve-test-workspaces"
    workspace.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        bug = workflow.create_bug(
            db,
            BugCreate(
                title="Missing username",
                description="Return Guest when user is None",
                repo="example/disposable",
                reporter="integration-test",
            ),
        )
        bug_id = bug.id

    validator = RealFixEngine.__new__(RealFixEngine)
    observed_feedback = []

    def attempt(request):
        observed_feedback.append(list(request.feedback))

        corrected = (
            WRONG_FIX if request.iteration == 1
            else CORRECT_FIX
        )

        with tempfile.TemporaryDirectory(
            prefix="docker-workflow-",
            dir=workspace,
        ) as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()

            subprocess.run(
                ["git", "init", "-q", str(repo)],
                check=True,
            )

            (repo / "app.py").write_text(
                ORIGINAL,
                encoding="utf-8",
            )
            (repo / "tests").mkdir()
            (repo / "tests/test_regression.py").write_text(
                REGRESSION,
                encoding="utf-8",
            )

            before = validator._verify_regression_test_before_fix(
                repo,
                "tests/test_regression.py",
            )
            assert before["passed"] is True, before

            patch = make_patch(corrected)
            after = validator._validate_patch(repo, patch)

            return FixResult(
                root_cause="Missing None handling",
                summary=f"Repair attempt {request.iteration}",
                plan=["Return Guest for None"],
                changed_files=[
                    {"path": "app.py", "diff": patch}
                ],
                test_results=after,
                branch=None,
            )

    fake_engine = Mock()
    fake_engine.propose_fix.side_effect = attempt

    set_engine(fake_engine)
    try:
        bug = workflow.run_iteration(bug_id)
    finally:
        set_engine(StubEngine())

    assert bug.status == AWAITING_REVIEW
    assert bug.iteration == 2
    assert fake_engine.propose_fix.call_count == 2

    assert bug.attempts[0]["outcome"] == "validation_failed"
    assert bug.attempts[1]["outcome"] == "pending_review"

    assert observed_feedback[0] == []
    assert any(
        "None == 'Guest'" in item
        for item in observed_feedback[1]
    )

    assert bug.test_results["passed"] is True
    fake_engine.merge.assert_not_called()


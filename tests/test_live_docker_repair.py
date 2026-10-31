
"""Controlled Docker repair validation without AI or GitHub."""

import difflib
import subprocess
import tempfile
from pathlib import Path

import pytest

from backend.orchestrator.real_engine import RealFixEngine

ORIGINAL = (
    "def get_username(user):\n"
    '    return user["name"]\n'
)

CORRECTED = (
    "def get_username(user):\n"
    "    if user is None:\n"
    '        return "Guest"\n'
    '    return user["name"]\n'
)

REGRESSION_TEST = (
    "from app import get_username\n\n"
    "def test_missing_user():\n"
    '    assert get_username(None) == "Guest"\n'
)


@pytest.fixture
def docker_tmp_path():
    """Create a disposable workspace accessible to the Docker daemon."""
    project_root = Path(__file__).resolve().parents[1]
    base = project_root / ".autoresolve-test-workspaces"
    base.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="docker-repair-",
        dir=base,
    ) as directory:
        yield Path(directory)


def test_real_docker_repair_flow(docker_tmp_path):
    """Bug must fail before patch and pass after patch."""

    tmp_path = docker_tmp_path

    repo = tmp_path / "example_repo"
    repo.mkdir()

    subprocess.run(
        ["git", "init", "-q", str(repo)],
        check=True,
    )

    (repo / "app.py").write_text(
        ORIGINAL,
        encoding="utf-8",
    )

    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_regression.py").write_text(
        REGRESSION_TEST,
        encoding="utf-8",
    )

    engine = RealFixEngine.__new__(RealFixEngine)

    # Stage 1: Regression test must fail before the fix.
    before = engine._verify_regression_test_before_fix(
        repo,
        "tests/test_regression.py",
    )

    assert before["passed"] is True, before

    # Stage 2: Generate a real Git patch.
    diff = "".join(
        difflib.unified_diff(
            ORIGINAL.splitlines(keepends=True),
            CORRECTED.splitlines(keepends=True),
            fromfile="a/app.py",
            tofile="b/app.py",
        )
    )

    patch = "diff --git a/app.py b/app.py\n" + diff

    # Stage 3: Apply patch and run Docker tests.
    after = engine._validate_patch(repo, patch)

    assert after["passed"] is True, after
    assert (repo / "app.py").read_text(
        encoding="utf-8"
    ) == CORRECTED

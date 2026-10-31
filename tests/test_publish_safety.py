
"""Verify AutoResolve stages only authorized repair files."""

import subprocess

import pytest

from backend.orchestrator.patch_safety import UnsafePatchError
from backend.orchestrator.publish_safety import stage_authorized_files


def git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def prepare_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    git(repo, "init", "-q")

    (repo / "app.py").write_text("value = 1\n")
    (repo / "unrelated.py").write_text("other = 1\n")

    git(repo, "add", "app.py", "unrelated.py")
    git(
        repo,
        "-c", "user.name=AutoResolve Test",
        "-c", "user.email=test@example.invalid",
        "commit", "-q", "-m", "Initial commit",
    )

    (repo / "tests").mkdir()
    (repo / "tests" / "test_regression.py").write_text(
        "def test_value():\n    assert True\n"
    )

    (repo / "app.py").write_text("value = 2\n")
    (repo / "unrelated.py").write_text("other = 999\n")

    (repo / ".env").write_text("LOCAL_TEST_ONLY=1\n")

    patch = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1 +1 @@\n"
        "-value = 1\n"
        "+value = 2\n"
    )

    return repo, patch


def test_stages_only_authorized_repair_files(tmp_path):
    repo, patch = prepare_repo(tmp_path)

    staged = stage_authorized_files(
        repo,
        patch,
        "tests/test_regression.py",
    )

    assert staged == [
        "app.py",
        "tests/test_regression.py",
    ]

    git_staged = git(
        repo, "diff", "--cached", "--name-only"
    ).stdout.splitlines()

    assert git_staged == staged
    assert "unrelated.py" not in git_staged
    assert ".env" not in git_staged


@pytest.mark.parametrize(
    "test_path",
    [
        "../outside.py",
        ".github/workflows/evil.py",
        "app.py",
        "tests/../app.py",
    ],
)
def test_rejects_unsafe_test_path(tmp_path, test_path):
    repo, patch = prepare_repo(tmp_path)

    with pytest.raises(UnsafePatchError):
        stage_authorized_files(repo, patch, test_path)


def test_rejects_preexisting_staged_changes(tmp_path):
    repo, patch = prepare_repo(tmp_path)

    git(repo, "add", "unrelated.py")

    with pytest.raises(
        UnsafePatchError,
        match="already contains staged changes",
    ):
        stage_authorized_files(
            repo,
            patch,
            "tests/test_regression.py",
        )

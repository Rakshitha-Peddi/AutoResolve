
from backend.orchestrator.engine import FixRequest
from backend.orchestrator.real_engine import RealFixEngine


def test_real_engine_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTORESOLVE_ENABLE_PUBLISH", "false")
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()

    (repo / "src" / "__init__.py").write_text("")
    (repo / "src" / "user_service.py").write_text(
        'def get_user_name(user):\n'
        '    return user["name"]\n'
    )

    (repo / "tests" / "test_user_service.py").write_text(
        "from src.user_service import get_user_name\n\n"
        "def test_get_user_name():\n"
        '    assert get_user_name({"name": "Albert"}) == "Albert"\n'
    )

    class FakeCodeEngine:
        def propose_fix(self, bug, repo_path, feedback=""):
            return {
                "analysis": {
                    "root_cause": "Missing None guard.",
                    "relevant_files": ["src/user_service.py"],
                    "confidence": "high",
                    "evidence": ["user is dereferenced without a guard."],
                    "context": [
                        (
                            "src/user_service.py",
                            (
                                'def get_user_name(user):\n'
                                '    return user["name"]\n'
                            ),
                        )
                    ],
                },
                "plan": [
                    "Add a None guard.",
                    "Add regression coverage.",
                ],
                "patch": (
                    "diff --git a/src/user_service.py b/src/user_service.py\n"
                    "--- a/src/user_service.py\n"
                    "+++ b/src/user_service.py\n"
                    "@@ -1,2 +1,2 @@\n"
                    " def get_user_name(user):\n"
                    '-    return user["name"]\n'
                    '+    return user["name"] if user is not None else None\n'
                ),
                "tests": {
                    "framework": "pytest",
                    "path": "tests/test_regression.py",
                    "summary": "Verify missing user returns None.",
                    "code": (
                        "from src.user_service import get_user_name\n\n"
                        "def test_missing_user():\n"
                        "    assert get_user_name(None) is None\n"
                    ),
                },
            }

    engine = object.__new__(RealFixEngine)
    engine.code_engine = FakeCodeEngine()

    request = FixRequest(
        bug_id="BUG-1",
        title="Missing user handling",
        description="get_user_name crashes when user is None",
        repo=str(repo),
        iteration=1,
    )

    monkeypatch.setattr(
        engine,
        "_clone_repository",
        lambda repo, destination: __import__("shutil").copytree(
            repo,
            destination,
        ),
    )

    result = engine.propose_fix(request)

    assert result.test_results["passed"] is True
    assert result.root_cause == "Missing None guard."
    assert any(
        item["path"] == "tests/test_regression.py"
        for item in result.changed_files
    )




def test_validate_patch_rejects_invalid_diff(tmp_path):
    import subprocess

    repo = tmp_path / "invalid_patch_repo"
    repo.mkdir()
    (repo / "example.py").write_text(
    "old_value = 1\n",
    encoding="utf-8",
    )

    subprocess.run(
        ["git", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    source_file = repo / "example.py"
    source_file.write_text("value = 1\n")

    subprocess.run(
        ["git", "add", "example.py"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    subprocess.run(
        [
            "git",
            "-c", "user.name=AutoResolve Test",
            "-c", "user.email=test@example.invalid",
            "commit",
            "-m", "Initial test file",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    engine = object.__new__(RealFixEngine)

    invalid_patch = (
        "--- a/example.py\n"
        "+++ b/example.py\n"
        "@@ -1 +1 @@\n"
        "-this line does not exist\n"
        "+value = 2\n"
    )

    result = engine._validate_patch(repo, invalid_patch)

    assert result["passed"] is False
    assert result["stage"] == "patch"



import pytest


def test_generated_test_rejects_symlink_outside_repository(tmp_path):
    repo = tmp_path / "repo"
    tests_dir = repo / "tests"
    outside_dir = tmp_path / "outside"

    tests_dir.mkdir(parents=True)
    outside_dir.mkdir()

    outside_file = outside_dir / "test_external.py"
    outside_file.write_text("# must not be overwritten\n")

    link = tests_dir / "test_external.py"
    link.symlink_to(outside_file)

    engine = object.__new__(RealFixEngine)

    with pytest.raises(
        RuntimeError,
        match="escapes the repository",
    ):
        engine._write_generated_test(
            repo,
            {
                "path": "tests/test_external.py",
                "code": "# AI-generated replacement\n",
            },
        )

    assert outside_file.read_text() == "# must not be overwritten\n"



def test_regression_test_fails_before_fix_and_passes_after_fix(tmp_path):
    import subprocess
    import sys

    repo = tmp_path / "regression_repo"
    src_dir = repo / "src"
    tests_dir = repo / "tests"

    src_dir.mkdir(parents=True)
    tests_dir.mkdir()

    (src_dir / "__init__.py").write_text("")
    source_file = src_dir / "user_service.py"
    source_file.write_text(
        'def get_user_name(user):\n'
        '    return user["name"]\n'
    )

    regression_test = tests_dir / "test_regression.py"
    regression_test.write_text(
        "from src.user_service import get_user_name\n\n"
        "def test_missing_user():\n"
        "    assert get_user_name(None) is None\n"
    )

    def run_regression_test():
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                str(regression_test),
            ],
            cwd=repo,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    # The test must catch the bug in the original implementation.
    before_fix = run_regression_test()
    assert before_fix.returncode != 0, (
        "The regression test unexpectedly passed before the fix."
    )

    # Apply the intended fix.
    source_file.write_text(
        "def get_user_name(user):\n"
        '    return user["name"] if user is not None else None\n'
    )

    # The same test must pass after the fix.
    after_fix = run_regression_test()
    assert after_fix.returncode == 0, (
        "The regression test failed after the fix.\n"
        + after_fix.stdout
        + after_fix.stderr
    )


def test_validate_patch_returns_failure_on_test_timeout(
    tmp_path,
    monkeypatch,
):
    import subprocess

    from backend.orchestrator.real_engine import RealFixEngine

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "example.py").write_text(
    "old_value = 1\n",
    encoding="utf-8",
)

    engine = object.__new__(RealFixEngine)

    def fake_worker(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["docker", "run", "pytest"],
            timeout=120,
        )

    monkeypatch.setattr(
        "backend.orchestrator.real_engine.run_pytest_in_worker",
        fake_worker,
    )
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "backend.orchestrator.real_engine.subprocess.run",
        fake_run,
    )


    result = engine._validate_patch(
        repo,
        "diff --git a/example.py b/example.py\n"
        "--- a/example.py\n"
        "+++ b/example.py\n"
        "@@ -1 +1 @@\n"
        "-old_value = 1\n"
        "+new_value = 2\n",
    )

    assert result["passed"] is False
    assert result["stage"] == "tests"
    assert "timed out" in result["error"].lower()

def test_validate_patch_returns_failure_on_apply_timeout(
    tmp_path,
    monkeypatch,
):
    import subprocess

    from backend.orchestrator.real_engine import RealFixEngine

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "example.py").write_text(
        "old_value = 1\n",
        encoding="utf-8",
    )
    engine = object.__new__(RealFixEngine)

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=30,
        )

    monkeypatch.setattr(
        "backend.orchestrator.real_engine.subprocess.run",
        fake_run,
    )

    result = engine._validate_patch(
        repo,
        "diff --git a/example.py b/example.py\n"
        "--- a/example.py\n"
        "+++ b/example.py\n"
        "@@ -1 +1 @@\n"
        "-old_value = 1\n"
        "+new_value = 2\n",
    )

    assert result["passed"] is False
    assert result["stage"] == "patch"
    assert "timed out" in result["error"].lower()


def test_propose_fix_cleans_up_temporary_workspace(
    tmp_path,
    monkeypatch,
):
    import shutil

    from backend.orchestrator.engine import FixRequest
    from backend.orchestrator.real_engine import RealFixEngine

    original_repo = tmp_path / "original"
    original_repo.mkdir()
    marker = original_repo / "keep.txt"
    marker.write_text("original content")

    engine = object.__new__(RealFixEngine)

    workspace_paths = []

    def fake_clone(repo, destination):
        workspace_paths.append(destination.parent)
        shutil.copytree(original_repo, destination)

    monkeypatch.setattr(engine, "_clone_repository", fake_clone)

    class FakeCodeEngine:
        def propose_fix(self, bug, repo_path, feedback=""):
            return {
                "analysis": {
                    "root_cause": "Test only.",
                    "relevant_files": ["keep.txt"],
                    "confidence": "high",
                    "evidence": ["Test evidence."],
                    "context": [],
                },
                "plan": ["Test cleanup."],
                "patch": (
                    "--- a/keep.txt\n"
                    "+++ b/keep.txt\n"
                    "@@ -1 +1 @@\n"
                    "-original content\n"
                    "+updated content\n"
                ),
                "tests": {
                    "framework": "pytest",
                    "path": "tests/test_regression.py",
                    "summary": "Test cleanup.",
                    "code": (
                        "def test_placeholder():\n"
                        "    assert True\n"
                    ),
                },
            }

    engine.code_engine = FakeCodeEngine()

    request = FixRequest(
        bug_id="BUG-CLEANUP",
        title="Cleanup test",
        description="Test temporary workspace cleanup",
        repo=str(original_repo),
        iteration=1,
    )

    result = engine.propose_fix(request)

    assert result.test_results["passed"] is False
    assert marker.read_text() == "original content"
    assert workspace_paths
    assert not workspace_paths[0].exists()

def test_validate_patch_rejects_path_outside_repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "example.py").write_text(
        "old_value = 1\n",
        encoding="utf-8",
    )

    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("original content\n")

    engine = object.__new__(RealFixEngine)

    malicious_patch = (
        "--- a/../outside.txt\n"
        "+++ b/../outside.txt\n"
        "@@ -1 +1 @@\n"
        "-original content\n"
        "+modified by malicious patch\n"
    )

    result = engine._validate_patch(repo, malicious_patch)

    assert result["passed"] is False
    assert result["stage"] == "patch"
    assert outside_file.read_text() == "original content\n"


def test_validate_patch_does_not_modify_file_through_external_symlink(
    tmp_path,
):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "example.py").write_text(
        "old_value = 1\n",
        encoding="utf-8",
    )

    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("original content\n")

    link = repo / "linked.txt"
    link.symlink_to(outside_file)

    subprocess.run(
        ["git", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    engine = object.__new__(RealFixEngine)

    malicious_patch = (
        "--- a/linked.txt\n"
        "+++ b/linked.txt\n"
        "@@ -1 +1 @@\n"
        "-original content\n"
        "+modified through symlink\n"
    )

    result = engine._validate_patch(repo, malicious_patch)

    assert result["passed"] is False
    assert result["stage"] == "patch"
    assert outside_file.read_text() == "original content\n"


def test_regression_gate_accepts_pytest_failure_summary(
    monkeypatch,
    tmp_path,
):
    import subprocess

    from backend.orchestrator import real_engine

    repo = tmp_path / "repo"
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_regression.py").write_text(
        "def test_regression():\n    assert False\n"
    )

    monkeypatch.setattr(
        real_engine,
        "run_pytest_in_worker",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["pytest"],
            returncode=1,
            stdout="F                                                                        [100%]\n"
                   "1 failed in 0.03s\n",
            stderr="",
        ),
    )

    engine = object.__new__(RealFixEngine)
    result = engine._verify_regression_test_before_fix(
        repo,
        "tests/test_regression.py",
    )

    assert result["passed"] is True
    assert result["stage"] == "regression_test_before_fix"


def test_regression_gate_rejects_unrelated_failed_text(
    monkeypatch,
    tmp_path,
):
    import subprocess

    from backend.orchestrator import real_engine

    repo = tmp_path / "repo"
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_regression.py").write_text(
        "def test_regression():\n    assert False\n"
    )

    monkeypatch.setattr(
        real_engine,
        "run_pytest_in_worker",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["pytest"],
            returncode=1,
            stdout="A setup operation failed unexpectedly.\n",
            stderr="",
        ),
    )

    engine = object.__new__(RealFixEngine)
    result = engine._verify_regression_test_before_fix(
        repo,
        "tests/test_regression.py",
    )

    assert result["passed"] is False
    assert result["stage"] == "regression_test_before_fix"


# ---- merge / publish behaviour -------------------------------------------

def test_merge_is_off_by_default(monkeypatch):
    import pytest

    monkeypatch.delenv("AUTORESOLVE_ENABLE_MERGE", raising=False)
    engine = object.__new__(RealFixEngine)
    with pytest.raises(RuntimeError, match="switched off"):
        engine.merge("owner/repo", "autoresolve/bug-1")


def test_merge_merges_the_open_pull_request(monkeypatch):
    from types import SimpleNamespace
    from unittest import mock

    import backend.orchestrator.real_engine as module

    monkeypatch.setenv("AUTORESOLVE_ENABLE_MERGE", "true")
    pull = mock.Mock(html_url="https://github.com/o/r/pull/1")
    pull.merge.return_value = SimpleNamespace(merged=True, message="ok")
    repo = mock.Mock()
    repo.owner.login = "o"
    repo.get_pulls.return_value = [pull]

    engine = object.__new__(RealFixEngine)
    engine.github_token = "token"
    with mock.patch.object(module, "Github") as github:
        github.return_value.get_repo.return_value = repo
        assert engine.merge("o/r", "autoresolve/bug-1") == pull.html_url

    repo.get_pulls.assert_called_once_with(state="open", head="o:autoresolve/bug-1")


def test_parse_model_json_accepts_code_fences():
    from ai_agent._json import parse_model_json

    assert parse_model_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_model_json('Here you go: {"a": 1} done') == {"a": 1}


def test_generated_test_cannot_overwrite_existing_file(tmp_path):
    from backend.orchestrator.real_engine import RealFixEngine

    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)

    existing = repo / "tests" / "test_security.py"
    existing.write_text(
        "def test_security():\n    assert True\n",
        encoding="utf-8",
    )

    engine = object.__new__(RealFixEngine)

    with pytest.raises(
        RuntimeError,
        match="already exists",
    ):
        engine._write_generated_test(
            repo,
            {
                "path": "tests/test_security.py",
                "code": (
                    "def test_security():\n"
                    "    assert False\n"
                ),
            },
        )

    assert existing.read_text(encoding="utf-8") == (
        "def test_security():\n    assert True\n"
    )


def test_generated_test_creates_new_file(tmp_path):
    from backend.orchestrator.real_engine import RealFixEngine

    repo = tmp_path / "repo"
    repo.mkdir()

    engine = object.__new__(RealFixEngine)

    result = engine._write_generated_test(
        repo,
        {
            "path": "tests/test_generated_regression.py",
            "code": "def test_regression():\n    assert True\n",
        },
    )

    assert result["path"] == "tests/test_generated_regression.py"
    assert (
        repo / "tests" / "test_generated_regression.py"
    ).read_text(encoding="utf-8") == (
        "def test_regression():\n    assert True\n"
    )

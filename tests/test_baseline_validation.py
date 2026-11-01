import subprocess

from backend.orchestrator.real_engine import RealFixEngine


def test_baseline_records_existing_test_failure(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_worker(repo_path, test_args=None, timeout=120):
        return subprocess.CompletedProcess(
            args=["pytest"],
            returncode=2,
            stdout="ERROR collecting test_3.py",
            stderr="",
        )

    monkeypatch.setattr(
        "backend.orchestrator.real_engine.run_pytest_in_worker",
        fake_worker,
    )

    engine = object.__new__(RealFixEngine)

    result = engine._run_baseline_tests(repo)

    assert result["available"] is True
    assert result["passed"] is False
    assert result["exit_code"] == 2
    assert "test_3.py" in result["stdout"]


def test_baseline_records_success(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_worker(repo_path, test_args=None, timeout=120):
        return subprocess.CompletedProcess(
            args=["pytest"],
            returncode=0,
            stdout="3 passed",
            stderr="",
        )

    monkeypatch.setattr(
        "backend.orchestrator.real_engine.run_pytest_in_worker",
        fake_worker,
    )

    engine = object.__new__(RealFixEngine)

    result = engine._run_baseline_tests(repo)

    assert result["available"] is True
    assert result["passed"] is True
    assert result["exit_code"] == 0
"""Safety gates for review-only partial validation."""

import subprocess

from backend.orchestrator.real_engine import RealFixEngine


def _validate(tmp_path, monkeypatch, baseline, after):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "test_2.py").write_text('print("Hello"\n')

    def fake_worker(_repo, test_args=None, timeout=120):
        if test_args:
            return subprocess.CompletedProcess(["pytest"], 0, "1 passed", "")
        return subprocess.CompletedProcess(["pytest"], 2, after, "")

    monkeypatch.setattr(
        "backend.orchestrator.real_engine.run_pytest_in_worker",
        fake_worker,
    )
    monkeypatch.setattr(
        "backend.orchestrator.real_engine.validate_patch_target",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "backend.orchestrator.real_engine.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
    )
    engine = object.__new__(RealFixEngine)
    patch = (
        "diff --git a/test_2.py b/test_2.py\n"
        "--- a/test_2.py\n+++ b/test_2.py\n"
        "@@ -1 +1 @@\n-print(\"Hello\"\n+print(\"Hello\")\n"
    )
    return engine._validate_patch(repo, patch, "tests/test_regression.py", baseline)


def test_partial_review_when_target_resolved_but_other_collection_error_remains(tmp_path, monkeypatch):
    baseline = {
        "available": True, "passed": False, "exit_code": 2,
        "stdout": "ERROR test_2.py\nERROR test_3.py\n", "stderr": "",
    }
    result = _validate(tmp_path, monkeypatch, baseline, "ERROR test_3.py\n")
    assert result["passed"] is False
    assert result["validation_level"] == "partial"
    assert result["partial_review_ready"] is True


def test_partial_review_rejected_when_new_error_appears(tmp_path, monkeypatch):
    baseline = {
        "available": True, "passed": False, "exit_code": 2,
        "stdout": "ERROR test_2.py\nERROR test_3.py\n", "stderr": "",
    }
    result = _validate(tmp_path, monkeypatch, baseline, "ERROR test_3.py\nERROR test_4.py\n")
    assert result["partial_review_ready"] is False


def test_partial_review_rejected_when_target_not_resolved(tmp_path, monkeypatch):
    baseline = {
        "available": True, "passed": False, "exit_code": 2,
        "stdout": "ERROR test_2.py\nERROR test_3.py\n", "stderr": "",
    }
    result = _validate(tmp_path, monkeypatch, baseline, "ERROR test_2.py\nERROR test_3.py\n")
    assert result["partial_review_ready"] is False

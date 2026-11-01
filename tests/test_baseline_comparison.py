from backend.orchestrator.baseline_comparison import (
    compare_failures,
    extract_failures,
)


def test_extract_collection_errors():
    output = (
        "================ short test summary info ================\n"
        "ERROR test_2.py\n"
        "ERROR test_3.py\n"
        "2 errors in 0.4s\n"
    )

    assert extract_failures(output) == {
        "test_2.py",
        "test_3.py",
    }


def test_comparison_identifies_resolved_failure():
    baseline = {
        "available": True,
        "exit_code": 2,
        "stdout": "ERROR test_2.py\nERROR test_3.py\n",
        "stderr": "",
    }

    current = {
        "exit_code": 2,
        "stdout": "ERROR test_3.py\n",
        "stderr": "",
    }

    result = compare_failures(baseline, current)

    assert result["comparison_available"] is True
    assert result["resolved_failures"] == ["test_2.py"]
    assert result["remaining_failures"] == ["test_3.py"]
    assert result["new_failures"] == []


def test_comparison_detects_new_failure():
    baseline = {
        "available": True,
        "exit_code": 1,
        "stdout": "FAILED tests/test_old.py::test_old\n",
        "stderr": "",
    }

    current = {
        "exit_code": 1,
        "stdout": (
            "FAILED tests/test_old.py::test_old\n"
            "FAILED tests/test_new.py::test_new\n"
        ),
        "stderr": "",
    }

    result = compare_failures(baseline, current)

    assert result["remaining_failures"] == [
        "tests/test_old.py::test_old"
    ]
    assert result["new_failures"] == [
        "tests/test_new.py::test_new"
    ]


def test_comparison_handles_unrecognized_output():
    baseline = {
        "available": True,
        "exit_code": 2,
        "stdout": "Collection interrupted",
        "stderr": "",
    }

    current = {
        "exit_code": 2,
        "stdout": "Collection interrupted",
        "stderr": "",
    }

    result = compare_failures(baseline, current)

    assert result["comparison_available"] is False

def test_validation_result_contains_failure_comparison(
    tmp_path,
    monkeypatch,
):
    import subprocess

    from backend.orchestrator.real_engine import RealFixEngine

    repo = tmp_path / "repo"
    repo.mkdir()

    source = repo / "example.py"
    source.write_text("value = 1\n", encoding="utf-8")

    def fake_worker(repo_path, test_args=None, timeout=120):
        return subprocess.CompletedProcess(
            args=["pytest"],
            returncode=2,
            stdout="ERROR test_3.py\n",
            stderr="",
        )

    monkeypatch.setattr(
        "backend.orchestrator.real_engine.run_pytest_in_worker",
        fake_worker,
    )

    def fake_apply(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "backend.orchestrator.real_engine.subprocess.run",
        fake_apply,
    )

    # This test isolates validation-result construction.
    monkeypatch.setattr(
        "backend.orchestrator.real_engine.validate_patch_target",
        lambda repo_path, patch: None,
    )

    baseline = {
        "available": True,
        "passed": False,
        "exit_code": 2,
        "stdout": "ERROR test_2.py\nERROR test_3.py\n",
        "stderr": "",
    }

    engine = object.__new__(RealFixEngine)

    result = engine._validate_patch(
        repo,
        "dummy patch",
        baseline=baseline,
    )

    assert result["passed"] is False
    assert result["stage"] == "baseline_blocked"

    comparison = result["failure_comparison"]

    assert comparison["comparison_available"] is True
    assert comparison["resolved_failures"] == ["test_2.py"]
    assert comparison["remaining_failures"] == ["test_3.py"]
    assert comparison["new_failures"] == []

"""Tests for safe validation-feedback selection."""

from backend.orchestrator.repair_feedback import build_repair_feedback


def test_failed_assertion_produces_feedback():
    result = {
        "passed": False,
        "stage": "tests",
        "exit_code": 1,
        "stdout": (
            "FAILED tests/test_regression.py::test_missing_user\n"
            "AssertionError: assert None == 'Guest'"
        ),
        "stderr": "",
    }

    feedback = build_repair_feedback(result)

    assert feedback is not None
    assert "None == 'Guest'" in feedback
    assert "ORIGINAL source code" in feedback


def test_success_does_not_produce_feedback():
    result = {
        "passed": True,
        "stage": "tests",
        "exit_code": 0,
        "stdout": "1 passed",
    }

    assert build_repair_feedback(result) is None


def test_docker_failure_is_not_retryable():
    result = {
        "passed": False,
        "stage": "tests",
        "error": "Docker worker unavailable",
    }

    assert build_repair_feedback(result) is None


def test_patch_failure_is_not_retryable():
    result = {
        "passed": False,
        "stage": "patch",
        "exit_code": 1,
        "stderr": "Patch does not apply",
    }

    assert build_repair_feedback(result) is None


def test_pytest_collection_failure_is_not_retryable():
    result = {
        "passed": False,
        "stage": "tests",
        "exit_code": 2,
        "stdout": "ERROR collecting tests/test_example.py",
    }

    assert build_repair_feedback(result) is None


def test_feedback_output_is_bounded():
    result = {
        "passed": False,
        "stage": "tests",
        "exit_code": 1,
        "stdout": "FAILED test_example\n" + "x" * 10000,
    }

    feedback = build_repair_feedback(result)

    assert feedback is not None
    assert len(feedback) < 3500

from pathlib import Path
from unittest.mock import Mock

from backend.orchestrator.workflow import AutoResolveWorkflow


def test_workflow_analyzes_bug():
    github_client = Mock()
    ai_engine = Mock()
    workspace_manager = Mock()
    patch_applier = Mock()
    test_runner = Mock()

    github_client.get_file.return_value = (
        "def divide(a, b):\n"
        "    return a / b\n"
    )

    ai_engine.analyze_bug.return_value = {
        "bug_found": True,
        "root_cause": "Division by zero",
        "affected_files": ["example.py"],
        "proposed_changes": [
            "Validate divisor before division."
        ],
        "patch_plan": [
            "Add zero check."
        ],
        "confidence": "high",
    }

    workflow = AutoResolveWorkflow(
        github_client=github_client,
        ai_engine=ai_engine,
        workspace_manager=workspace_manager,
        patch_applier=patch_applier,
        test_runner=test_runner,
    )

    result = workflow.analyze_bug(
        repo_url="https://github.com/example/project",
        bug_name="Division by zero",
        bug_description="Application crashes when b is zero.",
        relevant_files=["example.py"],
    )

    assert result["bug_name"] == "Division by zero"
    assert result["analysis"]["bug_found"] is True

    github_client.get_file.assert_called_once_with(
        "https://github.com/example/project",
        "example.py",
    )

    ai_engine.analyze_bug.assert_called_once()


def test_workflow_applies_patch_and_runs_tests():
    github_client = Mock()
    ai_engine = Mock()

    workspace_manager = Mock()
    workspace_manager.create_workspace.return_value = (
        Path("/tmp/autoresolve/repo")
    )

    patch_applier = Mock()

    test_runner = Mock()
    test_runner.run.return_value = {
        "success": True,
        "command": ["pytest", "-q"],
        "stdout": "10 passed",
        "stderr": "",
        "returncode": 0,
    }

    workflow = AutoResolveWorkflow(
        github_client=github_client,
        ai_engine=ai_engine,
        workspace_manager=workspace_manager,
        patch_applier=patch_applier,
        test_runner=test_runner,
    )

    result = workflow.apply_and_verify(
        repo_url="https://github.com/example/project",
        patch="fake patch",
    )

    assert result["success"] is True
    assert result["test_result"]["success"] is True

    workspace_manager.create_workspace.assert_called_once()
    patch_applier.apply_patch.assert_called_once()
    test_runner.run.assert_called_once()

    workspace_manager.cleanup.assert_called_once()
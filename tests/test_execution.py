from pathlib import Path
from unittest.mock import patch

from backend.orchestrator.execution.patch_applier import PatchApplier
from backend.orchestrator.execution.test_runner import TestRunner
from backend.orchestrator.execution.workspace import WorkspaceManager


def test_workspace_manager_creates_workspace():
    manager = WorkspaceManager()

    fake_workspace = Path("/tmp/autoresolve-test/repo")

    with patch(
        "backend.orchestrator.execution.workspace.subprocess.run"
    ) as mock_run, patch(
        "backend.orchestrator.execution.workspace.tempfile.mkdtemp",
        return_value="/tmp/autoresolve-test",
    ):
        workspace = manager.create_workspace(
            "https://github.com/example/project.git"
        )

    assert workspace == fake_workspace
    mock_run.assert_called_once()


def test_patch_applier_validates_and_applies_patch():
    patch_text = """\
diff --git a/example.py b/example.py
index 1234567..abcdefg 100644
--- a/example.py
+++ b/example.py
@@ -1 +1 @@
-old_value = 1
+old_value = 2
"""

    applier = PatchApplier()

    with patch(
        "backend.orchestrator.execution.patch_applier.subprocess.run"
    ) as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        applier.apply_patch(
            Path("/tmp/repository"),
            patch_text,
        )

    assert mock_run.call_count == 2


def test_test_runner_detects_pytest():
    runner = TestRunner()

    with patch.object(
        Path,
        "exists",
        return_value=True,
    ), patch.object(
        Path,
        "read_text",
        return_value="pytest>=8.0",
    ):
        command = runner._detect_test_command(
            Path("/tmp/repository")
        )

    assert command == ["pytest", "-q"]
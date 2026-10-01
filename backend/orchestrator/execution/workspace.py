import shutil
import subprocess
import tempfile
from pathlib import Path


class WorkspaceManager:
    """Create and manage an isolated local copy of a Git repository."""

    def __init__(self, timeout: int = 120):
        self.timeout = timeout

    def create_workspace(self, repo_url: str, branch: str = "main") -> Path:
        workspace = Path(tempfile.mkdtemp(prefix="autoresolve-"))

        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    branch,
                    repo_url,
                    str(workspace / "repo"),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise

        return workspace / "repo"

    def cleanup(self, workspace: Path) -> None:
        root = workspace

        if root.name == "repo":
            root = root.parent

        shutil.rmtree(root, ignore_errors=True)
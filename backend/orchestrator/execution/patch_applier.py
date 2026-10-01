import subprocess
from pathlib import Path


class PatchApplier:
    """Apply a unified diff inside an isolated repository workspace."""

    def apply_patch(self, workspace: Path, patch: str) -> None:
        if not patch.strip():
            raise ValueError("Patch is empty.")

        result = subprocess.run(
            ["git", "apply", "--check", "-"],
            cwd=workspace,
            input=patch,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Patch validation failed:\n"
                f"{result.stderr.strip()}"
            )

        result = subprocess.run(
            ["git", "apply", "-"],
            cwd=workspace,
            input=patch,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Patch application failed:\n"
                f"{result.stderr.strip()}"
            )
import subprocess
from pathlib import Path


class TestRunner:
    """Run the repository's test suite in an isolated workspace."""

    def run(self, workspace: Path) -> dict:
        command = self._detect_test_command(workspace)

        if command is None:
            return {
                "success": False,
                "command": None,
                "stdout": "",
                "stderr": "Unable to detect a supported test command.",
                "returncode": None,
            }

        result = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=120,
        )

        return {
            "success": result.returncode == 0,
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    @staticmethod
    def _detect_test_command(workspace: Path) -> list[str] | None:
        if (workspace / "pytest.ini").exists():
            return ["pytest", "-q"]

        if (workspace / "pyproject.toml").exists():
            pyproject = (workspace / "pyproject.toml").read_text(
                encoding="utf-8"
            )

            if "pytest" in pyproject:
                return ["pytest", "-q"]

        if (workspace / "requirements.txt").exists():
            requirements = (
                workspace / "requirements.txt"
            ).read_text(encoding="utf-8")

            if "pytest" in requirements:
                return ["pytest", "-q"]

        if (workspace / "package.json").exists():
            return ["npm", "test"]

        return None
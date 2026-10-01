"""Production FixEngine adapter.

Runs the AutoResolve repair pipeline against an isolated clone,
applies the generated source patch and regression test, then runs pytest.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from ai_agent.engine import CodeFixEngine
from backend.orchestrator.engine import FixEngine, FixRequest, FixResult


class RealFixEngine(FixEngine):
    """Run the real AI repair pipeline on an isolated GitHub clone."""

    def __init__(self):
        self.code_engine = CodeFixEngine()
        self.github_token = os.getenv("GITHUB_TOKEN")

        if not self.github_token:
            raise ValueError("GITHUB_TOKEN is not configured.")

    def _clone_repository(
        self,
        repo: str,
        destination: Path,
    ) -> None:
        if repo.startswith(("http://", "https://")):
            repo_url = repo.rstrip("/")
        else:
            repo_url = f"https://github.com/{repo}.git"

        askpass = destination.parent / "git-askpass.sh"

        askpass.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            '  *Username*) echo "x-access-token" ;;\n'
            '  *Password*) echo "$GITHUB_TOKEN" ;;\n'
            "esac\n"
        )
        askpass.chmod(0o700)

        env = os.environ.copy()
        env["GIT_ASKPASS"] = str(askpass)
        env["GIT_TERMINAL_PROMPT"] = "0"

        try:
            result = subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    repo_url,
                    str(destination),
                ],
                env=env,
                text=True,
                capture_output=True,
                timeout=120,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    result.stderr.strip()
                    or "Unable to clone GitHub repository."
                )
        finally:
            askpass.unlink(missing_ok=True)

    def propose_fix(self, request: FixRequest) -> FixResult:
        with tempfile.TemporaryDirectory(
            prefix="autoresolve-engine-"
        ) as temp:
            root = Path(temp)
            repo_path = root / "repo"

            self._clone_repository(
                request.repo,
                repo_path,
            )

            class BugInput:
                description = request.description

            feedback = "\n".join(request.feedback)

            result = self.code_engine.propose_fix(
                BugInput(),
                repo_path,
                feedback,
            )

            analysis = result["analysis"]
            patch = result["patch"]
            generated_test = result["tests"]

            if not patch:
                raise RuntimeError(
                    "AI pipeline produced an empty patch."
                )

            changed_files = self._patch_to_changed_files(
                patch
            )

            test_file = self._write_generated_test(
                repo_path,
                generated_test,
            )

            test_results = self._validate_patch(
                repo_path,
                patch,
            )

            if not test_results["passed"]:
                return FixResult(
                    root_cause=analysis["root_cause"],
                    summary=(
                        f"Attempt {request.iteration}: "
                        "validation failed."
                    ),
                    plan=result["plan"],
                    changed_files=changed_files + [test_file],
                    test_results=test_results,
                    branch=(
                        f"autoresolve/"
                        f"{request.bug_id.lower()}"
                    ),
                )

            changed_files.append(test_file)

            return FixResult(
                root_cause=analysis["root_cause"],
                summary=(
                    f"Attempt {request.iteration}: "
                    "automated repair proposed and validated."
                ),
                plan=result["plan"],
                changed_files=changed_files,
                test_results=test_results,
                branch=(
                    f"autoresolve/"
                    f"{request.bug_id.lower()}"
                ),
            )

    def _patch_to_changed_files(
        self,
        patch: str,
    ) -> list[dict]:
        paths: list[str] = []

        for line in patch.splitlines():
            if line.startswith("+++ b/"):
                path = line[6:].strip()

                if (
                    path != "/dev/null"
                    and path not in paths
                ):
                    paths.append(path)

        return [
            {
                "path": path,
                "diff": patch,
            }
            for path in paths
        ]

    def _write_generated_test(
        self,
        repo_path: Path,
        test_data: dict,
    ) -> dict:
        path = test_data.get("path")
        code = test_data.get("code")

        if not path or not code:
            raise RuntimeError(
                "AI generated an invalid regression test."
            )

        relative_path = Path(path)

        if relative_path.is_absolute():
            raise RuntimeError(
                "Generated test path must be relative."
            )

        if ".." in relative_path.parts:
            raise RuntimeError(
                "Generated test path escapes the repository."
            )

        if not str(relative_path).startswith("tests/"):
            raise RuntimeError(
                "Generated regression tests must live under tests/."
            )

        destination = repo_path / relative_path
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        destination.write_text(code)

        return {
            "path": str(relative_path),
            "diff": (
                "Generated regression test:\n\n"
                + code
            ),
        }

    def _validate_patch(
        self,
        repo_path: Path,
        patch: str,
    ) -> dict:
        apply_result = subprocess.run(
            [
                "git",
                "apply",
                "--whitespace=nowarn",
                "-",
            ],
            input=patch,
            text=True,
            cwd=repo_path,
            capture_output=True,
        )

        if apply_result.returncode != 0:
            return {
                "passed": False,
                "exit_code": apply_result.returncode,
                "stage": "patch",
                "stdout": apply_result.stdout[-12000:],
                "stderr": apply_result.stderr[-12000:],
            }

        test_result = subprocess.run(
            [
                os.environ.get("PYTHON", "python"),
                "-m",
                "pytest",
                "-q",
            ],
            cwd=repo_path,
            text=True,
            capture_output=True,
            timeout=120,
        )

        return {
            "passed": test_result.returncode == 0,
            "exit_code": test_result.returncode,
            "stage": "tests",
            "stdout": test_result.stdout[-12000:],
            "stderr": test_result.stderr[-12000:],
        }

    def merge(
        self,
        repo: str,
        branch: str | None,
    ) -> str | None:
        raise RuntimeError(
            "GitHub merge is not enabled yet. "
            "The current GitHub token is read-only."
        )
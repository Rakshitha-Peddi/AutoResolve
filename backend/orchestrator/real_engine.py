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
from backend.orchestrator.docker_worker import run_pytest_in_worker


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
        workspace_base = Path.home() / ".autoresolve-workspaces"
        workspace_base.mkdir(mode=0o700, parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="autoresolve-engine-",
            dir=workspace_base,
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

            regression_check = self._verify_regression_test_before_fix(
                repo_path,
                test_file["path"],
            )

            if not regression_check["passed"]:
                return FixResult(
                    root_cause=analysis["root_cause"],
                    summary=(
                        f"Attempt {request.iteration}: "
                        "regression test did not reproduce the bug "
                        "before the fix."
                    ),
                    plan=result["plan"],
                    changed_files=changed_files + [test_file],
                    test_results=regression_check,
                    branch=(
                        f"autoresolve/"
                        f"{request.bug_id.lower()}"
                    ),
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


        repo_root = repo_path.resolve()
        destination = (repo_root / relative_path).resolve()

        if not destination.is_relative_to(repo_root):
            raise RuntimeError(
                "Generated test path escapes the repository."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Re-resolve after creating directories to catch symlinks.
        destination = destination.resolve()

        if not destination.is_relative_to(repo_root):
            raise RuntimeError(
                "Generated test path escapes the repository."
            )

        destination.write_text(code)


        return {
            "path": str(relative_path),
            "diff": (
                "Generated regression test:\n\n"
                + code
            ),
        }

    def _verify_regression_test_before_fix(
        self,
        repo_path: Path,
        test_path: str,
    ) -> dict:
        relative_path = Path(test_path)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or not relative_path.is_relative_to("tests")
        ):
            return {
                "passed": False,
                "stage": "regression_test_path",
                "error": "Invalid regression test path.",
            }

        repo_root = repo_path.resolve()
        test_file = (repo_root / relative_path).resolve()

        if (
            not test_file.is_relative_to(repo_root)
            or not test_file.is_file()
        ):
            return {
                "passed": False,
                "stage": "regression_test_path",
                "error": "Regression test file is missing or unsafe.",
            }

        try:
            result = run_pytest_in_worker(
                repo_root,
                [relative_path.as_posix()],
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "stage": "regression_test_before_fix",
                "error": "Regression test timed out after 120 seconds.",
            }
        except (OSError, RuntimeError) as exc:
            return {
                "passed": False,
                "stage": "regression_test_before_fix",
                "error": f"Isolated worker failed: {exc}",
            }

        output = result.stdout + "\n" + result.stderr
        failed_test = (
            " failed" in output or " failed," in output
        )
        collection_error = (
            "ERROR collecting" in output
            or "ModuleNotFoundError" in output
            or "ImportError while loading conftest" in output
        )

        reproduced = (
            result.returncode != 0
            and failed_test
            and not collection_error
        )

        return {
            "passed": reproduced,
            "stage": "regression_test_before_fix",
            "exit_code": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
            "error": (
                None
                if reproduced
                else (
                    "The regression test did not demonstrate "
                    "a genuine failure before the fix."
                )
            ),
        }

    def _validate_patch(
        self,
        repo_path: Path,
        patch: str,
    ) -> dict:
        try:
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
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""

            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")

            return {
                "passed": False,
                "stage": "patch",
                "error": "Patch application timed out after 30 seconds.",
                "stdout": stdout[-12000:],
                "stderr": stderr[-12000:],
            }

        if apply_result.returncode != 0:
            return {
                "passed": False,
                "exit_code": apply_result.returncode,
                "stage": "patch",
                "stdout": apply_result.stdout[-12000:],
                "stderr": apply_result.stderr[-12000:],
            }

        try:
            test_result = run_pytest_in_worker(
                repo_path,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""

            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")

            return {
                "passed": False,
                "stage": "tests",
                "error": "Test suite timed out after 120 seconds.",
                "stdout": stdout[-12000:],
                "stderr": stderr[-12000:],
            }
        except (OSError, RuntimeError) as exc:
            return {
                "passed": False,
                "stage": "tests",
                "error": f"Isolated worker failed: {exc}",
                "stdout": "",
                "stderr": "",
            }

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
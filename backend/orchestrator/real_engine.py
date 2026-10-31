"""Production FixEngine adapter.

Runs the AutoResolve repair pipeline against an isolated clone,
applies the generated source patch and regression test, then runs pytest.
"""

from __future__ import annotations

import uuid
import os
import re
import subprocess
import tempfile
from pathlib import Path

from github import Github

from ai_agent.engine import CodeFixEngine
from backend.orchestrator.docker_worker import run_pytest_in_worker
from backend.orchestrator.engine import FixEngine, FixRequest, FixResult
from backend.orchestrator.patch_safety import (
    UnsafePatchError,
    validate_patch_target,
)
from backend.orchestrator.publish_safety import (
    stage_authorized_files,
)


def _merge_enabled() -> bool:
    """Pushing branches / merging is opt-in so a first run cannot touch GitHub."""
    return os.getenv("AUTORESOLVE_ENABLE_MERGE", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _publish_enabled() -> bool:
    """Publishing a validated branch and PR is separate from merging."""
    return os.getenv("AUTORESOLVE_ENABLE_PUBLISH", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


class RealFixEngine(FixEngine):
    """Run the real AI repair pipeline on an isolated GitHub clone."""


    def __init__(self):
        backend = os.getenv(
            "AUTORESOLVE_AI_BACKEND",
            "ollama",
        ).strip().lower()

        if backend == "ollama":
            # Preserve the existing local AI implementation.
            self.code_engine = CodeFixEngine()

        elif backend == "remote":
            # Import lazily so legacy mode needs no remote setup.
            from ai_agent.ai.bootstrap import build_ai_manager
            from ai_agent.ai.sync_adapter import SyncAIAdapter

            manager = build_ai_manager()
            adapter = SyncAIAdapter(manager)

            self.code_engine = CodeFixEngine(
                ai_adapter=adapter
            )

        else:
            raise ValueError(
                "AUTORESOLVE_AI_BACKEND must be "
                "'ollama' or 'remote'."
            )

        self.github_token = os.getenv("GITHUB_TOKEN")

        if not self.github_token:
            raise ValueError(
                "GITHUB_TOKEN is not configured."
            )


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
                check=False,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    result.stderr.strip()
                    or "Unable to clone GitHub repository."
                )
        finally:
            askpass.unlink(missing_ok=True)

    def propose_fix(self, request: FixRequest) -> FixResult:
        workspace_base = Path(
            os.getenv(
                "AUTORESOLVE_WORKSPACE_DIR",
                str(Path.home() / ".autoresolve-workspaces"),
            )
        )
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

            branch = f"autoresolve/{request.bug_id.lower()}"
            summary = (
                f"Attempt {request.iteration}: "
                "automated repair proposed and validated."
            )

            if _publish_enabled():
                branch, pr_url = self._publish_branch(
                    repo_path,
                    request,
                    analysis["root_cause"],
                    patch,
                    test_file["path"],
                )
                summary += f" Pull request opened: {pr_url}"

            return FixResult(
                root_cause=analysis["root_cause"],
                summary=summary,
                plan=result["plan"],
                changed_files=changed_files,
                test_results=test_results,
                branch=branch,
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

        if (
            not relative_path.parts
            or relative_path.parts[0] != "tests"
        ):
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

        # Never overwrite an existing repository test.
        # Exclusive creation also prevents a simple check-then-write race.
        try:
            with destination.open("x", encoding="utf-8") as test_file:
                test_file.write(code)
        except FileExistsError as exc:
            raise RuntimeError(
                "Generated regression test already exists."
            ) from exc


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
        # Require pytest's actual failure summary, not arbitrary
        # diagnostic text that happens to contain the word "failed".
        failed_test = bool(
            re.search(
                r"(?m)^\s*\d+\s+failed(?:,|\s|$)",
                output,
            )
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
            validate_patch_target(repo_path, patch)
        except (UnsafePatchError, OSError) as exc:
            return {
                "passed": False,
                "stage": "patch",
                "error": str(exc),
            }
        try:
            apply_result = subprocess.run(
                [
                    "git",
                    "apply",
                    "--recount",
                    "--whitespace=nowarn",
                    "-",
                ],
                input=patch,
                text=True,
                cwd=repo_path,
                capture_output=True,
                timeout=30,
                check=False,
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

    # ------------------------------------------------------------------
    # Publishing and merging (needs a GitHub token with write access)
    # ------------------------------------------------------------------

    @staticmethod
    def _repo_slug(repo: str) -> str:
        """'owner/repo' from either 'owner/repo' or a GitHub URL."""
        if repo.startswith(("http://", "https://")):
            from backend.orchestrator.github_client import GitHubClient

            return GitHubClient.parse_repo_url(repo)
        return repo.strip().removesuffix(".git")

    def _publish_branch(
        self,
        repo_path: Path,
        request: FixRequest,
        root_cause: str,
        patch: str,
        regression_test_path: str,
    ) -> tuple[str, str]:
        """Commit the validated change, push a branch and open a pull request.

        Nothing is merged here. The merge happens only after the developer
        presses "Approve & Merge" (see merge()).
        """
        slug = self._repo_slug(request.repo)
        branch = (
            f"autoresolve/{request.bug_id.lower()}"
            f"-attempt-{request.iteration}-{uuid.uuid4().hex[:8]}"
        )

        askpass = repo_path.parent / "git-askpass-push.sh"
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
        env["GITHUB_TOKEN"] = self.github_token

        def git(*args: str) -> None:
            result = subprocess.run(
                ["git", *args],
                cwd=repo_path,
                env=env,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"git {args[0]} failed: {result.stderr.strip()[-500:]}"
                )

        try:
            git("checkout", "-b", branch)

            stage_authorized_files(
                repo_path,
                patch,
                regression_test_path,
            )

            git(
                "-c", "user.name=AutoResolve",
                "-c", "user.email=autoresolve@users.noreply.github.com",
                "commit", "-m",
                f"AutoResolve: {request.bug_id} {request.title}"[:200],
            )
            git("push", "origin", branch)
        finally:
            askpass.unlink(missing_ok=True)

        gh_repo = Github(self.github_token).get_repo(slug)
        pull = gh_repo.create_pull(
            title=f"AutoResolve {request.bug_id}: {request.title}"[:250],
            body=(
                f"Automated fix proposed by AutoResolve for {request.bug_id}.\n\n"
                f"**Root cause:** {root_cause}\n\n"
                "The regression test failed before the fix and the full test "
                "suite passed after it. A human must approve before merge."
            ),
            head=branch,
            base=gh_repo.default_branch,
        )
        return branch, pull.html_url

    def merge(
        self,
        repo: str,
        branch: str | None,
    ) -> str | None:
        """Merge the pull request for an approved fix and return its URL."""
        if not _merge_enabled():
            raise RuntimeError(
                "Merging is switched off. Set AUTORESOLVE_ENABLE_MERGE=true "
                "in .env (and use a GitHub token with write access)."
            )
        if not branch:
            raise RuntimeError("This fix has no branch to merge.")

        gh_repo = Github(self.github_token).get_repo(self._repo_slug(repo))
        pulls = list(
            gh_repo.get_pulls(
                state="open",
                head=f"{gh_repo.owner.login}:{branch}",
            )
        )
        if not pulls:
            raise RuntimeError(f"No open pull request found for branch '{branch}'.")

        pull = pulls[0]
        outcome = pull.merge(merge_method="squash")
        if not outcome.merged:
            raise RuntimeError(f"GitHub refused the merge: {outcome.message}")
        return pull.html_url

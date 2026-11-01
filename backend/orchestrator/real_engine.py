"""Production FixEngine adapter.

Runs the AutoResolve repair pipeline against an isolated clone,
applies the generated source patch and regression test, then runs pytest.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from github import Github

from ai_agent.engine import CodeFixEngine
from backend.orchestrator.baseline_comparison import compare_failures
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
            baseline = self._run_baseline_tests(repo_path)

            class BugInput:
                title = request.title
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
                unique_name=True,
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
                test_file["path"],
                baseline,
            )

            # A partially validated repair may be published only for
            # explicit human review, never represented as a full pass.
            partial_review = (
                test_results.get("partial_review_ready") is True
                and _publish_enabled()
            )
            if not test_results["passed"] and not partial_review:
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
            if partial_review:
                test_results["review_ready"] = True

            branch = f"autoresolve/{request.bug_id.lower()}"
            summary = (
                f"Attempt {request.iteration}: "
                + (
                    "targeted repair passed; full suite still has "
                    "pre-existing failures (partial validation)."
                    if partial_review
                    else "automated repair proposed and validated."
                )
            )

            if _publish_enabled():
                branch, pr_url = self._publish_branch(
                    repo_path,
                    request,
                    analysis["root_cause"],
                    patch,
                    test_file["path"],
                    test_results,
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
        *,
        unique_name: bool = False,
    ) -> dict:
        """Write a new regression test without replacing existing files."""
        path = test_data.get("path")
        code = test_data.get("code")

        if not isinstance(path, str) or not isinstance(code, str):
            raise RuntimeError(  # noqa: TRY004
                "AI generated an invalid regression test."
            )

        if not path.strip() or not code.strip():
            raise RuntimeError("AI generated an empty regression test.")

        relative_path = Path(path.replace("\\", "/"))

        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuntimeError("Generated test path escapes the repository.")

        if (
            not relative_path.parts
            or relative_path.parts[0] != "tests"
            or relative_path.suffix != ".py"
        ):
            raise RuntimeError(
                "Generated regression tests must be Python files under tests/."
            )

        repo_root = repo_path.resolve()

        # Reject unsafe existing directories and symlinks.
        parent = repo_root
        for component in relative_path.parts[:-1]:
            parent = parent / component
            if parent.is_symlink():
                raise RuntimeError(
                    "Generated test path escapes the repository."
                )

        parent.mkdir(parents=True, exist_ok=True)

        if not parent.resolve().is_relative_to(repo_root):
            raise RuntimeError(
                "Generated test path escapes the repository."
            )

        stem = relative_path.stem
        suffix = relative_path.suffix

        # Try the requested filename, then unused numbered alternatives.
        for number in range(101):
            # Live repairs use globally unique names across separate clones,
            # bugs, attempts, repositories and concurrent workers.
            name = (
                f"test_autoresolve_{uuid.uuid4().hex}.py"
                if unique_name
                else (
                    relative_path.name
                    if number == 0
                    else f"{stem}_autoresolve_{number}{suffix}"
                )
            )

            candidate = parent / name

            if candidate.is_symlink():
                raise RuntimeError(
                    "Generated test path escapes the repository."
                )

            try:
                # Exclusive creation: never overwrite existing files.
                with candidate.open("x", encoding="utf-8") as test_file:
                    test_file.write(code)

            except FileExistsError:
                continue

            actual_path = candidate.relative_to(repo_root).as_posix()

            return {
                "path": actual_path,
                "diff": "Generated regression test:\n\n" + code,
            }

        raise RuntimeError(
            "Could not allocate a unique regression test filename."
        )

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

    def _run_baseline_tests(self, repo_path: Path) -> dict:
        """Record existing repository test failures before a repair."""

        try:
            result = run_pytest_in_worker(
                repo_path,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "available": False,
                "error": "Baseline test run timed out.",
            }
        except (OSError, RuntimeError) as exc:
            return {
                "passed": False,
                "available": False,
                "error": f"Baseline worker failed: {exc}",
            }

        return {
            "passed": result.returncode == 0,
            "available": True,
            "exit_code": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
        }

    def _validate_patch(
        self,
        repo_path: Path,
        patch: str,
        regression_test_path: str | None = None,
        baseline: dict | None = None,
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

# Verify the generated regression test after applying the patch.
        if regression_test_path is not None:
            try:
                focused_result = run_pytest_in_worker(
                    repo_path,
                    [regression_test_path],
                    timeout=120,
                )
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                return {
                    "passed": False,
                    "stage": "focused_regression",
                    "error": f"Focused regression validation failed: {exc}",
                }

            if focused_result.returncode != 0:
                return {
                    "passed": False,
                    "stage": "focused_regression",
                    "exit_code": focused_result.returncode,
                    "stdout": focused_result.stdout[-12000:],
                    "stderr": focused_result.stderr[-12000:],
                    "error": "Generated regression test failed after the patch.",
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

        full_suite_passed = test_result.returncode == 0
        comparison = (
            compare_failures(
                baseline,
                {
                    "exit_code": test_result.returncode,
                    "stdout": test_result.stdout,
                    "stderr": test_result.stderr,
                },
            )
            if baseline is not None
            else {
                "comparison_available": False,
                "resolved_failures": [],
                "remaining_failures": [],
                "new_failures": [],
            }
        )

        if baseline is not None and not baseline.get("available", True):
            return {
                "passed": False,
                "stage": "baseline_unavailable",
                "exit_code": test_result.returncode,
                "error": baseline.get(
                    "error",
                    "Repository baseline could not be established.",
                ),
                "stdout": test_result.stdout[-12000:],
                "stderr": test_result.stderr[-12000:],
            }

        baseline_failed = (
            baseline is not None
            and baseline.get("available", True)
            and baseline.get("passed") is False
        )

        # Partial review is deliberately narrow. It cannot certify the
        # full suite: collection may stop before discovering every error.
        changed_paths = self._patch_to_changed_files(patch)
        changed_source_paths = {item["path"] for item in changed_paths}
        resolved = set(comparison.get("resolved_failures", []))
        remaining = set(comparison.get("remaining_failures", []))
        partial_review_ready = (
            regression_test_path is not None
            and baseline is not None
            and baseline.get("available") is True
            and baseline.get("exit_code") == 2
            and test_result.returncode == 2
            and comparison.get("comparison_available") is True
            and not comparison.get("new_failures")
            and bool(remaining)
            and bool(changed_source_paths & resolved)
            and len(changed_source_paths) == 1
        )

        return {
            "passed": full_suite_passed,
            "partial_review_ready": partial_review_ready,
            "validation_level": (
                "full" if full_suite_passed
                else "partial" if partial_review_ready
                else "failed"
            ),
            "exit_code": test_result.returncode,
            "stage": (
                "baseline_blocked"
                if baseline_failed and not full_suite_passed
                else "tests"
            ),
            "baseline_passed": (
                baseline.get("passed")
                if baseline is not None
                else None
            ),
            "focused_regression_passed": (
                True if regression_test_path is not None else None
            ),
            "failure_comparison": comparison,
            "error": (
                "The full repository suite still fails. "
                "Pre-existing failures were present in the baseline; "
                "additional failures have not been ruled out."
                if baseline_failed and not full_suite_passed
                else None
            ),
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
        test_results: dict | None = None,
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
        partial = bool(
            test_results and test_results.get("review_ready") is True
        )
        comparison = (test_results or {}).get("failure_comparison") or {}
        if partial:
            validation_note = (
                "**PARTIAL VALIDATION — FULL TEST SUITE FAILED.**\n"
                "The generated regression failed before the patch and "
                "passed afterward. The repository still has pre-existing "
                "pytest collection failures. Other failures may be hidden "
                "by interrupted collection. Review carefully before merging.\n\n"
                f"Remaining observed failures: "
                f"{', '.join(comparison.get('remaining_failures', []))}\n"
            )
        else:
            validation_note = (
                "Generated regression failed before the patch; the full "
                "test suite passed afterward.\n"
            )
        pull = gh_repo.create_pull(
            title=(
                f"[PARTIAL] AutoResolve {request.bug_id}: {request.title}"
                if partial
                else f"AutoResolve {request.bug_id}: {request.title}"
            )[:250],
            body=(
                f"Automated fix proposed by AutoResolve for {request.bug_id}.\n\n"
                f"**Root cause:** {root_cause}\n\n"
                + validation_note
                + "\nA human must review and explicitly approve before merge."
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
        # GitHub may report null while it computes mergeability. Only an
        # explicit False is a confirmed conflict; never overwrite either side.
        if pull.mergeable is False:
            raise RuntimeError(
                "PR has merge conflicts with the current default branch. "
                "Do not retry approval on this unchanged PR; regenerate "
                "and revalidate the fix from the latest repository state. "
                f"PR: {pull.html_url}"
            )
        outcome = pull.merge(merge_method="squash")
        if not outcome.merged:
            raise RuntimeError(f"GitHub refused the merge: {outcome.message}")
        return pull.html_url

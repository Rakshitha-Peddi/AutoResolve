
"""Restrict AutoResolve commits to validated repair files."""

import subprocess
from pathlib import Path

from backend.orchestrator.patch_safety import (
    UnsafePatchError,
    validate_patch_target,
)


def stage_authorized_files(
    repo_path: Path,
    patch: str,
    regression_test_path: str,
) -> list[str]:
    """Stage exactly one source file and one generated regression test."""
    root = Path(repo_path).resolve(strict=True)

    # Revalidate the source target at the publishing boundary.
    source_path = validate_patch_target(root, patch)

    test_path = Path(regression_test_path)

    if (
        test_path.is_absolute()
        or ".." in test_path.parts
        or "\\" in regression_test_path
        or len(test_path.parts) < 2
        or test_path.parts[0] != "tests"
        or test_path.suffix != ".py"
        or any(part.startswith(".") for part in test_path.parts)
    ):
        raise UnsafePatchError(
            "Regression test path is not authorized."
        )

    candidate = root

    for part in test_path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise UnsafePatchError(
                "Regression test path contains a symbolic link."
            )

    resolved = candidate.resolve(strict=True)

    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise UnsafePatchError(
            "Regression test must be an existing repository file."
        )

    allowed = {source_path, test_path.as_posix()}

    if len(allowed) != 2:
        raise UnsafePatchError(
            "Source file and regression test must be different."
        )

    def git(*args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Git staging validation failed: {args[0]}."
            )
        return result

    # Reject any changes that were already staged.
    pre_staged = git(
        "diff", "--cached", "--name-only", "-z"
    ).stdout

    if pre_staged:
        raise UnsafePatchError(
            "Repository index already contains staged changes."
        )

    git(
        "add",
        "-A",
        "--",
        source_path,
        test_path.as_posix(),
    )

    staged_output = git(
        "diff", "--cached", "--name-only", "-z"
    ).stdout

    staged = set(staged_output.split("\0")) - {""}

    if staged != allowed:
        raise UnsafePatchError(
            "Staged changes do not match authorized repair files."
        )

    return sorted(staged)


"""Conservative authorization of single-file Python repair patches."""

from pathlib import Path


class UnsafePatchError(ValueError):
    """The proposed patch violates repository modification policy."""


def validate_patch_target(repo_path: Path, patch: str) -> str:
    """Authorize a single existing Python file before git apply.

    This validates the target and patch headers. Git remains
    responsible for validating the unified-diff syntax and hunks.
    """
    root = Path(repo_path).resolve(strict=True)

    if not root.is_dir():
        raise UnsafePatchError("Repository root is not a directory.")

    lines = patch.splitlines()
    headers = [
        line for line in lines
        if line.startswith("diff --git ")
    ]

    if len(headers) != 1 or not lines or lines[0] != headers[0]:
        raise UnsafePatchError(
            "Patch must modify exactly one existing source file."
        )

    header = headers[0]
    parts = header.split(" ")

    if len(parts) != 4:
        raise UnsafePatchError("Invalid patch header.")

    old_name, new_name = parts[2:]

    if not old_name.startswith("a/") or not new_name.startswith("b/"):
        raise UnsafePatchError("Invalid Git patch paths.")

    relative = old_name[2:]

    if not relative or relative != new_name[2:]:
        raise UnsafePatchError(
            "Patch must preserve the original file path."
        )

    path = Path(relative)

    if (
        path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or "\\" in relative
        or path.suffix != ".py"
        or "tests" in path.parts
        or any(part.startswith(".") for part in path.parts)
    ):
        raise UnsafePatchError("Patch target is not authorized.")

    # Disallow file creation, deletion, renaming, mode changes,
    # binary patches and other extended Git patch operations.
    forbidden = (
        "new file mode ",
        "deleted file mode ",
        "old mode ",
        "new mode ",
        "rename from ",
        "rename to ",
        "copy from ",
        "copy to ",
        "GIT binary patch",
        "Binary files ",
        "index ",
    )

    if any(
        line.startswith(forbidden)
        for line in lines[1:]
    ):
        raise UnsafePatchError(
            "Patch contains unsupported Git metadata."
        )

    source_headers = [
        line for line in lines
        if line.startswith("--- ")
    ]

    destination_headers = [
        line for line in lines
        if line.startswith("+++ ")
    ]

    if source_headers != [f"--- a/{relative}"]:
        raise UnsafePatchError(
            "Patch contains inconsistent source-file headers."
        )

    if destination_headers != [f"+++ b/{relative}"]:
        raise UnsafePatchError(
            "Patch contains inconsistent destination-file headers."
        )

    if not any(line.startswith("@@ ") for line in lines):
        raise UnsafePatchError("Patch contains no change hunks.")

    candidate = root

    for part in path.parts:
        candidate = candidate / part

        if candidate.is_symlink():
            raise UnsafePatchError(
                "Patch target contains a symbolic link."
            )

    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise UnsafePatchError(
            "Patch target is missing or cannot be resolved."
        ) from exc

    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise UnsafePatchError(
            "Patch target is missing or outside the repository."
        )

    return relative

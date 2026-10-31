
"""Security tests for the repair patch authorization boundary."""

import pytest

from backend.orchestrator.patch_safety import (
    UnsafePatchError,
    validate_patch_target,
)


def make_patch(path):
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        "-value = 1\n"
        "+value = 2\n"
    )


def test_allows_existing_python_file(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")

    assert validate_patch_target(
        tmp_path,
        make_patch("app.py"),
    ) == "app.py"


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        ".github/workflows/build.py",
        "tests/test_app.py",
        ".env",
        "config.json",
        ".git/hooks/hook.py",
    ],
)
def test_rejects_unauthorized_paths(tmp_path, path):
    with pytest.raises(UnsafePatchError):
        validate_patch_target(
            tmp_path,
            make_patch(path),
        )


def test_rejects_symlink_target(tmp_path):
    outside = tmp_path.parent / "outside_patch_target.py"
    outside.write_text("value = 1\n")

    (tmp_path / "linked.py").symlink_to(outside)

    with pytest.raises(UnsafePatchError, match="symbolic link"):
        validate_patch_target(
            tmp_path,
            make_patch("linked.py"),
        )


def test_rejects_multiple_file_patches(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")
    (tmp_path / "other.py").write_text("value = 1\n")

    patch = make_patch("app.py") + make_patch("other.py")

    with pytest.raises(UnsafePatchError, match="exactly one"):
        validate_patch_target(tmp_path, patch)


def test_rejects_file_creation(tmp_path):
    patch = (
        "diff --git a/new.py b/new.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/new.py\n"
        "@@ -0,0 +1 @@\n"
        "+value = 1\n"
    )

    with pytest.raises(UnsafePatchError):
        validate_patch_target(tmp_path, patch)


def test_rejects_missing_source_file(tmp_path):
    with pytest.raises(UnsafePatchError):
        validate_patch_target(
            tmp_path,
            make_patch("missing.py"),
        )


def test_rejects_extra_destination_header(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")

    patch = make_patch("app.py") + "+++ b/config.py\n"

    with pytest.raises(
        UnsafePatchError,
        match="destination-file headers",
    ):
        validate_patch_target(tmp_path, patch)


def test_rejects_extra_source_header(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")

    patch = make_patch("app.py") + "--- a/config.py\n"

    with pytest.raises(
        UnsafePatchError,
        match="source-file headers",
    ):
        validate_patch_target(tmp_path, patch)


def test_rejects_git_metadata(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")

    patch = make_patch("app.py").replace(
        "--- a/app.py\n",
        "rename from app.py\n--- a/app.py\n",
    )

    with pytest.raises(
        UnsafePatchError,
        match="unsupported Git metadata",
    ):
        validate_patch_target(tmp_path, patch)

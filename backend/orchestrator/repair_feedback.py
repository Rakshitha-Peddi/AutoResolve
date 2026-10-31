
"""Prepare bounded validation feedback for a subsequent repair attempt."""

MAX_FEEDBACK_CHARS = 3000

RETRYABLE_STAGES = frozenset({
    "tests",
})


def build_repair_feedback(result: dict) -> str | None:
    """Return repair guidance for a genuine test failure.

    Infrastructure errors, patch application failures, and pre-fix
    regression failures are not automatically retried.
    """
    if result.get("passed") is not False:
        return None

    if result.get("stage") not in RETRYABLE_STAGES:
        return None

    # An actual pytest failure exits with 1. Other exit codes may
    # indicate collection errors, interruptions, or configuration issues.
    if result.get("exit_code") != 1:
        return None

    output = "\n".join(
        str(result.get(key) or "")
        for key in ("stdout", "stderr")
    ).strip()

    if (
        "FAILED " not in output
        and "AssertionError" not in output
    ):
        return None

    # Keep API prompts bounded. Test logs can contain arbitrary
    # repository data; use only trusted, disposable test inputs
    # until sensitive-output redaction is implemented.
    output = output[-MAX_FEEDBACK_CHARS:]

    return (
        "The previous patch applied but failed regression tests.\n"
        "Generate a corrected patch from the ORIGINAL source code.\n"
        "Do not repeat the previous incorrect behavior.\n"
        "Satisfy the exact expected behavior in the bug report.\n"
        "Preserve behavior for previously working inputs.\n\n"
        "Validation failure:\n"
        f"{output}"
    )

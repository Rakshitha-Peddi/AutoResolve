"""Compare recognizable pytest failures before and after a repair."""

import re

FAILURE_PATTERN = re.compile(
    r"(?m)^(?:ERROR|FAILED)\s+(\S+)"
)


def extract_failures(output: str) -> set[str]:
    """Extract pytest failure identifiers from summary lines."""
    return set(FAILURE_PATTERN.findall(output))


def compare_failures(
    baseline: dict,
    current: dict,
) -> dict:
    """Report resolved, unchanged and newly observed failures."""

    before_output = (
        str(baseline.get("stdout") or "")
        + "\n"
        + str(baseline.get("stderr") or "")
    )

    after_output = (
        str(current.get("stdout") or "")
        + "\n"
        + str(current.get("stderr") or "")
    )

    before = extract_failures(before_output)
    after = extract_failures(after_output)

    # Do not claim a reliable comparison if failure identifiers
    # cannot be extracted from a failing pytest run.
    reliable = (
        baseline.get("available") is True
        and (
            baseline.get("exit_code") == 0
            or bool(before)
        )
        and (
            current.get("exit_code") == 0
            or bool(after)
        )
    )

    if not reliable:
        return {
            "comparison_available": False,
            "resolved_failures": [],
            "remaining_failures": [],
            "new_failures": [],
        }

    return {
        "comparison_available": True,
        "resolved_failures": sorted(before - after),
        "remaining_failures": sorted(before & after),
        "new_failures": sorted(after - before),
    }
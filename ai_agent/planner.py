class Planner:
    """Create a constrained repair plan from the bug analysis."""

    def plan(self, analysis, feedback=""):
        relevant_files = analysis.get("relevant_files", [])

        steps = [
            "Confirm the reported failure from the available source-code evidence.",
            "Modify only the relevant code path.",
            "Preserve existing public behaviour outside the reported bug.",
            "Add or update regression coverage for the failure.",
            "Run the repository test suite and verify the repair.",
        ]

        if relevant_files:
            steps.insert(
                1,
                "Inspect and modify: " + ", ".join(relevant_files),
            )

        if feedback:
            steps.append(
                f"Developer constraint: {feedback}"
            )

        return steps
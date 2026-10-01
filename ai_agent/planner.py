class Planner:
    def plan(self, analysis, feedback=""):
        steps = ["Preserve the public API", "Make the smallest safe change", "Add regression coverage"]
        if feedback:
            steps.append(f"Honor developer constraint: {feedback}")
        return steps

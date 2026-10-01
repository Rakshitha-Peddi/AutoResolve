class Analyzer:
    def analyze(self, bug, context):
        # Deterministic demo analysis; production mode can be backed by an LLM client.
        relevant = [x[1] for x in context]
        description = (bug.description or "").lower()
        if "none" in description or "null" in description:
            cause = "The user lookup dereferences a missing user record without guarding the None/null case."
        else:
            cause = "The failure is localized to the highest-ranked repository context returned by retrieval."
        return {
            "root_cause": cause,
            "relevant_files": relevant,
            "confidence": "high" if relevant else "low",
            "evidence": [x[1] for x in context[:3]],
        }

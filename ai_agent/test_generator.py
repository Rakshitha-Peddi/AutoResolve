class TestGenerator:
    def generate(self, bug, feedback=""):
        return {
            "framework": "pytest",
            "files": ["tests/test_user_service.py"],
            "summary": "Regression test for missing user record.",
            "feedback_constraints": feedback,
        }

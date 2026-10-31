from .analyzer import Analyzer
from .fixer import Fixer
from .planner import Planner
from .retriever import RepositoryRetriever
from .test_generator import RegressionTestGenerator


class CodeFixEngine:
    """Coordinate retrieval, analysis, planning, fixing and test generation."""

    def __init__(self, ai_adapter=None):
        self.retriever = RepositoryRetriever()
        self.planner = Planner()

        if ai_adapter is None:
            # Preserve existing local Ollama behavior.
            self.analyzer = Analyzer()
            self.fixer = Fixer()
            self.test_generator = RegressionTestGenerator()
        else:
            # Share one configured AI manager across all components.
            self.analyzer = Analyzer(ai_adapter=ai_adapter)
            self.fixer = Fixer(ai_adapter=ai_adapter)
            self.test_generator = RegressionTestGenerator(
                ai_adapter=ai_adapter
            )

    def propose_fix(self, bug, repo_path, feedback=""):
        # 1. Retrieve relevant repository code.
        context = self.retriever.retrieve(
            repo_path,
            bug.description,
        )

        if not context:
            raise RuntimeError(
                "Repository retrieval found no relevant source files."
            )

        # 2. Analyze the bug using the retrieved source.
        analysis = self.analyzer.analyze(
            bug,
            context,
        )

        # 3. Create the repair plan.
        plan = self.planner.plan(
            analysis,
            feedback,
        )

        # 4. Generate the actual source-code patch.
        fixer_feedback = (
            "ORIGINAL BUG REQUIREMENTS:\n"
            f"{bug.description}\n\n"
            "PREVIOUS VALIDATION FEEDBACK:\n"
            f"{feedback or 'None'}"
        )

        patch = self.fixer.generate(
            repo_path,
            analysis,
            fixer_feedback,
        )

        # 5. Generate regression-test information.
        tests = self.test_generator.generate(
            bug,
            feedback,
            analysis.get("context", []),
        )

        return {
            "analysis": analysis,
            "plan": plan,
            "patch": patch,
            "tests": tests,
        }
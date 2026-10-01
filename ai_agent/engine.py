from .retriever import RepositoryRetriever
from .analyzer import Analyzer
from .planner import Planner
from .fixer import Fixer
from .test_generator import RegressionTestGenerator


class CodeFixEngine:
    """Coordinate retrieval, analysis, planning, fixing and test generation."""

    def __init__(self):
        self.retriever = RepositoryRetriever()
        self.analyzer = Analyzer()
        self.planner = Planner()
        self.fixer = Fixer()
        self.test_generator = RegressionTestGenerator()

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
        patch = self.fixer.generate(
            repo_path,
            analysis,
            feedback,
        )

        # 5. Generate regression-test information.
        tests = self.test_generator.generate(
            bug,
            feedback,
        )

        return {
            "analysis": analysis,
            "plan": plan,
            "patch": patch,
            "tests": tests,
        }
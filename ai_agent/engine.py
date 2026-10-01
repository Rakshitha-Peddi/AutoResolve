import json
from pathlib import Path
from .retriever import RepositoryRetriever
from .analyzer import Analyzer
from .planner import Planner
from .fixer import Fixer
from .test_generator import TestGenerator

class CodeFixEngine:
    def __init__(self):
        self.retriever = RepositoryRetriever()
        self.analyzer = Analyzer()
        self.planner = Planner()
        self.fixer = Fixer()
        self.test_generator = TestGenerator()

    def propose_fix(self, bug, repo_path, feedback=""):
        context = self.retriever.retrieve(repo_path, bug.description)
        analysis = self.analyzer.analyze(bug, context)
        plan = self.planner.plan(analysis, feedback)
        patch = self.fixer.generate(repo_path, analysis, feedback)
        tests = self.test_generator.generate(bug, feedback)
        return {"analysis": analysis, "plan": plan, "patch": patch, "tests": tests}

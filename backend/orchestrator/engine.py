"""The connection point to the AI and execution layers.

workflow.py only ever talks to a ``FixEngine``. The real engine (retriever ->
analyzer -> planner -> fixer -> test generator -> isolated test run -> git
branch / pull request) plugs in here without touching anything else:

    from backend.orchestrator.engine import set_engine
    set_engine(MyEngine())

Until then ``StubEngine`` returns placeholder results so the whole flow works.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class FixEngineError(Exception):
    """Raise this from an engine for an expected failure with a readable message."""


@dataclass
class FixRequest:
    bug_id: str                     # e.g. "BUG-7"
    title: str
    description: str
    repo: str
    iteration: int                  # 1 for the first attempt
    feedback: list[str] = field(default_factory=list)  # every change request so far, oldest first


@dataclass
class FixResult:
    root_cause: str
    summary: str                    # one-line description of the fix
    plan: list[str]
    changed_files: list[dict]       # [{"path": "src/x.py", "diff": "<unified diff>"}]
    test_results: dict              # {"passed": bool, "total": int, "failed": int, "tests": [...]}
    branch: Optional[str] = None    # branch or pull request the merge step will use


class FixEngine(ABC):
    @abstractmethod
    def propose_fix(self, request: FixRequest) -> FixResult:
        """Analyse the bug and return a validated fix. May take minutes."""

    @abstractmethod
    def merge(self, repo: str, branch: Optional[str]) -> Optional[str]:
        """Merge an approved change. Return a short reference (commit or PR URL) if there is one."""


class StubEngine(FixEngine):
    """Placeholder: invents a plausible result, touches no repository."""

    def propose_fix(self, request: FixRequest) -> FixResult:
        n = request.iteration
        path = "src/example.py"
        added = [f'+    # {request.bug_id}: guard against the reported failure']
        plan = [
            "Locate the code path named in the bug report",
            "Add the smallest safe change that removes the failure",
            "Add a regression test that reproduces the bug",
        ]
        for i, constraint in enumerate(request.feedback, start=1):
            plan.append(f"Developer constraint {i}: {constraint}")
            added.append(f"+    # constraint {i}: {constraint[:60]}")
        diff = "\n".join([
            f"--- a/{path}", f"+++ b/{path}", "@@ -10,3 +10,{} @@".format(3 + len(added)),
            " def handle(value):", *added, "     return value",
        ])
        tests = [
            {"name": "test_existing_behaviour", "passed": True},
            {"name": f"test_{request.bug_id.lower().replace('-', '_')}_regression", "passed": True},
        ]
        return FixResult(
            root_cause=f"(stub) Missing guard for the case described in: {request.title}",
            summary=f"(stub) Attempt {n}: placeholder fix for {request.bug_id}",
            plan=plan,
            changed_files=[{"path": path, "diff": diff}, {
                "path": "tests/test_example.py",
                "diff": "--- a/tests/test_example.py\n+++ b/tests/test_example.py\n@@ -1,0 +1,3 @@\n"
                        "+def test_regression():\n+    assert True\n+",
            }],
            test_results={"passed": True, "total": len(tests), "failed": 0, "tests": tests},
            branch=f"autoresolve/{request.bug_id.lower()}",
        )

    def merge(self, repo: str, branch: Optional[str]) -> Optional[str]:
        return f"stub-merge:{branch}"


_engine: FixEngine = StubEngine()


def set_engine(engine: FixEngine) -> None:
    global _engine
    _engine = engine


def get_engine() -> FixEngine:
    return _engine

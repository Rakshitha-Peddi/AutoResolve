from pathlib import Path

from backend.orchestrator.engine import FixRequest
from backend.orchestrator.real_engine import RealFixEngine


def test_real_engine_pipeline(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()

    (repo / "src" / "__init__.py").write_text("")
    (repo / "src" / "user_service.py").write_text(
        'def get_user_name(user):\n'
        '    return user["name"]\n'
    )

    (repo / "tests" / "test_user_service.py").write_text(
        "from src.user_service import get_user_name\n\n"
        "def test_get_user_name():\n"
        '    assert get_user_name({"name": "Albert"}) == "Albert"\n'
    )

    class FakeCodeEngine:
        def propose_fix(self, bug, repo_path, feedback=""):
            return {
                "analysis": {
                    "root_cause": "Missing None guard.",
                    "relevant_files": ["src/user_service.py"],
                    "confidence": "high",
                    "evidence": ["user is dereferenced without a guard."],
                    "context": [
                        (
                            "src/user_service.py",
                            (
                                'def get_user_name(user):\n'
                                '    return user["name"]\n'
                            ),
                        )
                    ],
                },
                "plan": [
                    "Add a None guard.",
                    "Add regression coverage.",
                ],
                "patch": (
                    "--- a/src/user_service.py\n"
                    "+++ b/src/user_service.py\n"
                    "@@ -1,2 +1,2 @@\n"
                    " def get_user_name(user):\n"
                    '-    return user["name"]\n'
                    '+    return user["name"] if user is not None else None\n'
                ),
                "tests": {
                    "framework": "pytest",
                    "path": "tests/test_regression.py",
                    "summary": "Verify missing user returns None.",
                    "code": (
                        "from src.user_service import get_user_name\n\n"
                        "def test_missing_user():\n"
                        "    assert get_user_name(None) is None\n"
                    ),
                },
            }

    engine = object.__new__(RealFixEngine)
    engine.code_engine = FakeCodeEngine()

    request = FixRequest(
        bug_id="BUG-1",
        title="Missing user handling",
        description="get_user_name crashes when user is None",
        repo=str(repo),
        iteration=1,
    )

    monkeypatch.setattr(
        engine,
        "_clone_repository",
        lambda repo, destination: __import__("shutil").copytree(
            repo,
            destination,
        ),
    )

    result = engine.propose_fix(request)

    assert result.test_results["passed"] is True
    assert result.root_cause == "Missing None guard."
    assert any(
        item["path"] == "tests/test_regression.py"
        for item in result.changed_files
    )

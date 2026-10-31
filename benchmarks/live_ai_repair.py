
"""Controlled live AI repair test on a disposable repository."""

import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

from ai_agent.ai.bootstrap import build_ai_manager
from ai_agent.ai.sync_adapter import SyncAIAdapter
from ai_agent.engine import CodeFixEngine
from backend.orchestrator.real_engine import RealFixEngine

ORIGINAL_CODE = (
    "def get_username(user):\n"
    '    return user["name"]\n'
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_BASE = PROJECT_ROOT / ".autoresolve-test-workspaces"


def main():
    load_dotenv(PROJECT_ROOT / ".env")

    manager = build_ai_manager()
    adapter = SyncAIAdapter(manager)
    code_engine = CodeFixEngine(ai_adapter=adapter)

    WORKSPACE_BASE.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="live-ai-repair-",
        dir=WORKSPACE_BASE,
    ) as directory:
        repo = Path(directory) / "repo"
        repo.mkdir()

        subprocess.run(
            ["git", "init", "-q", str(repo)],
            check=True,
        )

        (repo / "app.py").write_text(
            ORIGINAL_CODE,
            encoding="utf-8",
        )

        bug = SimpleNamespace(
            description=(
                "In app.py, get_username(user) crashes when "
                "user is None because it indexes user['name']. "
                "Expected behavior: return 'Guest' for None. "
                "For valid dictionaries, preserve the original "
                "name lookup behavior. Add a minimal None guard."
            )
        )

        print("Generating live AI analysis, patch, and test...")

        result = code_engine.propose_fix(
            bug=bug,
            repo_path=repo,
        )

        print("\nRoot cause:")
        print(result["analysis"]["root_cause"])

        print("\nGenerated patch:")
        print(result["patch"])

        print("\nGenerated regression test:")
        print(result["tests"]["code"])

        # RealFixEngine methods can validate a local workspace
        # without cloning or publishing anything to GitHub.
        validator = RealFixEngine.__new__(RealFixEngine)

        test_file = validator._write_generated_test(
            repo,
            result["tests"],
        )

        print("\nChecking regression test before the fix...")
        before = validator._verify_regression_test_before_fix(
            repo,
            test_file["path"],
        )

        if not before["passed"]:
            print("Pre-fix regression validation failed:")
            print(before)
            raise RuntimeError(
                "Generated test did not reproduce the bug."
            )

        print("Regression test reproduced the bug.")

        print("\nApplying patch and testing in Docker...")
        after = validator._validate_patch(
            repo,
            result["patch"],
        )

        if not after["passed"]:
            print("Post-fix validation failed:")
            print(after)
            raise RuntimeError(
                "Generated fix failed validation."
            )

        print("Docker validation passed.")
        print("Live AI repair pipeline completed successfully.")

    print("Disposable repository cleaned up.")


if __name__ == "__main__":
    main()

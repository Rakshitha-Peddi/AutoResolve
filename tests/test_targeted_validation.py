import difflib
import subprocess
import tempfile
from pathlib import Path

from backend.orchestrator.real_engine import RealFixEngine


def test_targeted_validation_ignores_unrelated_broken_files():
    project_root = Path(__file__).resolve().parents[1]
    workspace = project_root / ".autoresolve-test-workspaces"
    workspace.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="targeted-validation-",
        dir=workspace,
    ) as directory:
        repo = Path(directory) / "repo"
        repo.mkdir()

        subprocess.run(
            ["git", "init", "-q"],
            cwd=repo,
            check=True,
        )

        original = 'print("9+0")\n'
        corrected = 'print(9+0)\n'

        (repo / "test_7.py").write_text(original)

        # These files would break a repository-wide pytest run.
        (repo / "test_2.py").write_text('print("Hello"\n')
        (repo / "test_6.py").write_text("a = input()\n")

        tests = repo / "tests"
        tests.mkdir()

        regression_path = "tests/test_autoresolve_target.py"

        (repo / regression_path).write_text(
            "import io\n"
            "import runpy\n"
            "from contextlib import redirect_stdout\n"
            "\n"
            "def test_output():\n"
            "    output = io.StringIO()\n"
            "    with redirect_stdout(output):\n"
            "        runpy.run_path('test_7.py')\n"
            "    assert output.getvalue().strip() == '9'\n"
        )

        patch = (
            "diff --git a/test_7.py b/test_7.py\n"
            + "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    corrected.splitlines(keepends=True),
                    fromfile="a/test_7.py",
                    tofile="b/test_7.py",
                )
            )
        )

        engine = object.__new__(RealFixEngine)

        # Confirm the regression fails before applying the patch.
        before = engine._verify_regression_test_before_fix(
            repo,
            regression_path,
        )

        assert before["passed"] is True, before

        # Apply patch and run only the targeted regression.
        after = engine._validate_targeted_patch(
            repo,
            patch,
            regression_path,
        )

        assert after["passed"] is True, after
        assert after["validation_level"] == "targeted"
        assert after["focused_regression_passed"] is True
        assert after["full_suite_passed"] is None
        assert (repo / "test_7.py").read_text() == corrected

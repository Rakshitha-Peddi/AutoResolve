import ast
import sys
import subprocess
import json
import os

from .ollama_client import generate_text

from ._json import parse_model_json


class RegressionTestGenerator:
    """Generate regression-test code for a reported bug."""

    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

    @staticmethod
    def _repair_missing_imports(code, context):
        """Add imports for uniquely identified repository functions."""
        if not context:
            return code

        tree = ast.parse(code)
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            )
        }

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.update(
                    alias.asname or alias.name
                    for alias in node.names
                )
            elif isinstance(node, ast.Import):
                imported.update(
                    alias.asname or alias.name.split(".")[0]
                    for alias in node.names
                )

        candidates = {}

        for path, source in context:
            if not path.endswith(".py"):
                continue

            try:
                source_tree = ast.parse(source)
            except SyntaxError:
                continue

            module = path.replace("\\", "/").removesuffix(".py")
            module = module.replace("/", ".")

            if module.endswith(".__init__"):
                module = module.removesuffix(".__init__")

            if not module or not module.isidentifier() and any(
                not part.isidentifier() for part in module.split(".")
            ):
                continue

            for node in source_tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    candidates.setdefault(node.name, set()).add(module)

        needed = set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
                continue

            name = node.id
            if name in defined or name in imported:
                continue

            modules = candidates.get(name, set())
            if len(modules) == 1:
                needed.add((next(iter(modules)), name))

        if not needed:
            return code

        imports = "\n".join(
            f"from {module} import {name}"
            for module, name in sorted(needed)
        )

        return imports + "\n\n" + code

    def generate(self, bug, feedback="", context=None):
        repository_code = "\n\n".join(
            f"FILE: {path}\n{content}"
            for path, content in (context or [])
        ) or "(not available)"

        prompt = f"""
You are the regression-test component of AutoResolve.

Generate a focused regression test for this bug.

BUG:
{bug.description}

DEVELOPER FEEDBACK:
{feedback or "None"}

REPOSITORY CODE (use these real module paths and function names in imports):
{repository_code}

Requirements:

1. Write a regression test that asserts the CORRECT behavior after the bug is fixed.
   Do NOT write a test that expects or accepts the reported bug or exception.
2. The test must FAIL on the original buggy code and PASS after a correct fix.
   For a crash caused by invalid input, call the affected function directly
   and assert its expected return value or other correct behavior.
   Do NOT use pytest.raises() to expect the reported crash.
3. Follow the repository's existing testing conventions.
   The test file path MUST start with tests/ and must import only modules that exist above.
   The test must FAIL on the current (unfixed) code and PASS once the bug is fixed.
4. Do not test unrelated behavior.
5. Return a complete test file or a complete test function.
6. Use pytest unless the bug clearly requires another framework.
7. Do not use Markdown code fences.
8. Generate the smallest possible regression test.
9. Prefer one pytest test function with a single focused assertion.
10. Keep the Python test code under 15 lines.
11. Do not include explanations, comments, or unrelated tests in the code.
12. Test functions MUST have zero parameters. Do not use pytest fixtures.
13. Import the tested function or module explicitly.
14. Create all test inputs inside the test function.

Return ONLY valid JSON:

{{
  "framework": "pytest",
  "path": "tests/test_regression.py",
  "summary": "what the regression test verifies",
  "code": "complete Python test code"
}}
"""

        text = generate_text(prompt, self.model)

        try:
            result = parse_model_json(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AI test generator returned invalid JSON."
            ) from exc

        if not isinstance(result, dict):
            raise RuntimeError(
                "AI test generator returned an invalid response structure."
            )


        required = ("framework", "path", "summary", "code")

        for field in required:
            value = result.get(field)

            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(
                    f"AI test generator returned an invalid '{field}' field."
                )
        # Repair missing imports when the repository identifies them.
        try:
            result["code"] = self._repair_missing_imports(
                result["code"],
                context,
            )
        except SyntaxError as exc:
            raise RuntimeError(
                f"AI-generated regression test has invalid Python syntax: {exc}"
            ) from exc

        # Reject generated tests containing undefined Python names.
        lint_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--select",
                "F821",
                "--stdin-filename",
                "tests/test_regression.py",
                "-",
            ],
            input=result["code"],
            text=True,
            capture_output=True,
            timeout=30,
        )

        if lint_result.returncode != 0:
            raise RuntimeError(
                "AI-generated regression test failed static validation:\n"
                + lint_result.stdout
                + lint_result.stderr
            )
        # Reject generated tests that depend on unexpected pytest fixtures.
        try:
            tree = ast.parse(result["code"])
        except SyntaxError as exc:
            raise RuntimeError(
                f"AI-generated regression test has invalid Python syntax: {exc}"
            ) from exc

        test_functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]

        if not test_functions:
            raise RuntimeError(
                "AI-generated regression test contains no test function."
            )

        for function in test_functions:
            args = function.args
            if (
                args.posonlyargs
                or args.args
                or args.kwonlyargs
                or args.vararg
                or args.kwarg
            ):
                raise RuntimeError(
                    "AI-generated regression test uses function parameters "
                    "or pytest fixtures."
                )
        return result

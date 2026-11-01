import difflib
import json
import logging
import os
from pathlib import Path

from ._json import parse_model_json
from .ollama_client import generate_text
from .source_safety import contains_sensitive_source

logger = logging.getLogger(__name__)


class Fixer:
    """Generate repository-specific patches using an AI coding model."""

    def __init__(self, ai_adapter=None):
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
        self.ai_adapter = ai_adapter

    def generate(self, repo_path, analysis, feedback=""):
        context = analysis.get("context", [])
        allowed_files = [path for path, _content in context]

        files_text = "\n\n".join(
            f"FILE: {path}\n{content}"
            for path, content in context
        )

        prompt = f"""
You are a Python code repair assistant.

BUG:
{analysis.get("root_cause", "")}

REPOSITORY FILES:
{files_text}

FEEDBACK:
{feedback or "None"}

Fix the bug with the smallest possible change.

IMPORTANT CORRECTNESS REQUIREMENTS:
- The fix must satisfy the expected behavior stated in the bug report.
- Preventing an exception is insufficient if the returned value is incorrect.
- Never invent a default value. Use the exact expected value from the bug report.
- Preserve existing behavior for inputs that already work.
- If the bug report explicitly requires "Guest", return "Guest", not None.
- Prefer an explicit guard condition when handling None.
- Ensure the corrected code would pass a regression test for the expected behavior.

ALLOWED FILE PATHS:
{chr(10).join(f"- {path}" for path in allowed_files)}

FILE SELECTION RULES:
- You MUST choose file_path from ALLOWED FILE PATHS.
- Copy the selected file_path exactly as written.
- Do not add the repository name or an absolute directory.
- Do not invent another filename.
- Do not modify a file that is not provided.

Return ONLY a valid JSON object with these fields:

{{
  "summary": "one short sentence describing the fix",
  "root_cause": "one short sentence explaining the bug",
  "file_path": "repository-relative path of the source file",
  "corrected_code": "complete corrected contents of that file"
}}

Rules:
1. Change exactly one Python source file.
2. Do not modify test files.
3. Preserve all existing functions, return types, and working behavior.
4. Return the complete corrected source file, not a diff.
5. Make the smallest possible change. Do not rewrite unrelated code.
6. Do not include Markdown code fences or explanations.
7. Existing valid inputs must produce exactly the same outputs as before.
8. Handle the reported failing input with a separate, minimal condition.
9. Do not replace an existing return expression for valid inputs with a different value.
10. If the bug involves None, add an explicit None check before accessing its attributes or keys.
11. Preserve the original return statement for non-None inputs.
"""

        if getattr(self, "ai_adapter", None) is not None:
            text = self.ai_adapter.generate_text(
                prompt=prompt,
                task="bug_fix",
                max_tokens=65536,
            )
        else:
            text = generate_text(
                prompt,
                self.model,
                max_tokens=65536,
            )


        try:
            result = parse_model_json(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AI fixer returned invalid JSON."
            ) from exc

        if not isinstance(result, dict):
            # Invalid model output is a pipeline failure.
            raise RuntimeError(  # noqa: TRY004
                "AI fixer returned an invalid response structure."
            )

        for field in (
            "summary",
            "root_cause",
            "file_path",
            "corrected_code",
        ):
            if (
                not isinstance(result.get(field), str)
                or not result[field].strip()
            ):
                raise RuntimeError(
                    f"AI fixer returned an invalid '{field}' field."
                )

        # Validate the AI-selected source file.
        relative_path = Path(
            result["file_path"].replace("\\", "/")
        )

        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.suffix != ".py"
            or "tests" in relative_path.parts
        ):
            raise RuntimeError(
                "AI fixer selected an unsafe source file."
            )

        # The model may modify only files supplied by the retriever.
        retrieved_paths = {
            Path(path.replace("\\", "/")).as_posix()
            for path, _content in context
        }

        if relative_path.as_posix() not in retrieved_paths:
            logger.warning(
                "AI selected unsupported file '%s'. Retrieved files: %s",
                relative_path.as_posix(),
                sorted(retrieved_paths),
            )
            raise RuntimeError(
                "AI fixer selected a file that was not retrieved."
            )

        repo_root = Path(repo_path).resolve()

        # Reject symlinks in the source path, including parent directories.
        candidate = repo_root
        for part in relative_path.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise RuntimeError(
                    "AI fixer selected an unsafe symlink path."
                )

        source_file = candidate.resolve()

        if (
            not source_file.is_relative_to(repo_root)
            or not source_file.is_file()
        ):
            raise RuntimeError(
                "AI fixer selected a missing or unsafe file."
            )

        original = source_file.read_text(encoding="utf-8")
        # The source must still match the version supplied to the AI.
        retrieved_content = {
            Path(path.replace("\\", "/")).as_posix(): content
            for path, content in context
        }

        if original != retrieved_content[relative_path.as_posix()]:
            raise RuntimeError(
                "AI fixer detected that the source file changed "
                "after repository retrieval."
            )
        if contains_sensitive_source(original):
            raise RuntimeError(
                "AI fixer cannot modify a file containing sensitive content."
            )
        corrected = result["corrected_code"]
        # Preserve the source file's final newline convention.
        if original.endswith("\n") and not corrected.endswith("\n"):
            corrected += "\n"

        if corrected == original:
            raise RuntimeError(
                "AI fixer did not change the source code. "
                "The generated corrected_code was identical to the "
                "original file. Regenerate a minimal, meaningful change "
                "that fixes the reported behavior."
            )

        # Check that the corrected code is valid Python.
        try:
            compile(corrected, str(relative_path), "exec")
        except SyntaxError as exc:
            raise RuntimeError(
                f"AI fixer generated invalid Python: {exc}"
            ) from exc

        # Generate the Git patch deterministically.
        git_path = relative_path.as_posix()

        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                corrected.splitlines(keepends=True),
                fromfile=f"a/{git_path}",
                tofile=f"b/{git_path}",
            )
        )

        patch = (
            f"diff --git a/{git_path} b/{git_path}\n"
            + diff
        )

        return patch
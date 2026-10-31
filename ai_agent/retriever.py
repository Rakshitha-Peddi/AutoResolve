
"""Retrieve bounded Python source code from a repository."""

import os
from pathlib import Path

from .source_safety import contains_sensitive_source

MAX_FILE_BYTES = 128 * 1024
MAX_CONTEXT_CHARS = 12000
MAX_MATCHES = 8

EXCLUDED_DIRECTORIES = frozenset({
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    ".autoresolve_data",
    ".autoresolve-test-workspaces",
})

EXCLUDED_FILENAMES = frozenset({
    ".env",
    ".env.example",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.json",
    "secrets.py",
    "settings_local.py",
})

ALLOWED_EXTENSIONS = frozenset({".py"})


class RepositoryRetriever:
    """Select limited source context without following repository symlinks."""

    def retrieve(self, repo_path: str, query: str):
        root = Path(repo_path).resolve(strict=True)

        if not root.is_dir():
            raise ValueError("Repository path must be a directory.")

        terms = [
            word.lower()
            for word in query.replace("?", " ").replace(".", " ").split()
            if len(word) > 2
        ]

        if not terms:
            return []

        matches = []

        for current_dir, directories, filenames in os.walk(
            root,
            followlinks=False,
        ):
            current = Path(current_dir)

            directories[:] = [
                name
                for name in directories
                if name not in EXCLUDED_DIRECTORIES
                and not name.startswith(".")
                and not (current / name).is_symlink()
            ]

            for filename in filenames:
                if filename.startswith("."):
                    continue

                if filename.lower() in EXCLUDED_FILENAMES:
                    continue

                path = current / filename

                if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                    continue

                if path.is_symlink():
                    continue

                try:
                    resolved = path.resolve(strict=True)

                    if not resolved.is_relative_to(root):
                        continue

                    if not resolved.is_file():
                        continue

                    if resolved.stat().st_size > MAX_FILE_BYTES:
                        continue

                    # Bound the read itself rather than truncating
                    # only after loading an arbitrarily large file.
                    with resolved.open("rb") as source:
                        data = source.read(MAX_FILE_BYTES + 1)

                    if len(data) > MAX_FILE_BYTES or b"\x00" in data:
                        continue

                    text = data.decode("utf-8")
                    if contains_sensitive_source(text):
                        continue
                except (OSError, UnicodeError):
                    continue

                score = sum(
                    term in text.lower()
                    for term in terms
                )

                if score:
                    relative_path = path.relative_to(root).as_posix()
                    matches.append(
                        (
                            score,
                            relative_path,
                            text[:MAX_CONTEXT_CHARS],
                        )
                    )

        matches.sort(key=lambda item: (-item[0], item[1]))

        return matches[:MAX_MATCHES]

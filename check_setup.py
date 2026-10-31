
"""Offline configuration checks for AutoResolve 2.0.

Run:
    python3 check_setup.py

This script does not make AI or GitHub API requests.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)

failures = 0


def check(condition, message, fix=""):
    global failures

    symbol = "[ OK ]" if condition else "[FAIL]"
    print(f"{symbol} {message}")

    if not condition:
        failures += 1
        if fix:
            print(f"       -> {fix}")


def info(message):
    print(f"[INFO] {message}")


def main():
    print("\nAutoResolve 2.0 — Setup Check\n")

    check(
        sys.version_info >= (3, 10),
        f"Python version: {sys.version.split()[0]}",
        "Install Python 3.10 or newer.",
    )

    required = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "sqlalchemy": "sqlalchemy",
        "dotenv": "python-dotenv",
        "github": "PyGithub",
        "pytest": "pytest",
    }

    missing = [
        package
        for module, package in required.items()
        if importlib.util.find_spec(module) is None
    ]

    check(
        not missing,
        "Python dependencies installed",
        f"Install missing packages: {', '.join(missing)}"
        if missing else "",
    )

    check(
        (ROOT / ".env").is_file(),
        ".env configuration file exists",
        "Copy .env.example to .env and configure it.",
    )

    real_engine = os.getenv(
        "AUTORESOLVE_REAL_ENGINE", "false"
    ).strip().lower() in {"true", "1", "yes", "on"}

    backend = os.getenv(
        "AUTORESOLVE_AI_BACKEND", "ollama"
    ).strip().lower()

    info(
        "Engine mode: REAL"
        if real_engine else
        "Engine mode: STUB (safe demo mode)"
    )

    check(
        backend in {"remote", "ollama"},
        f"AI backend: {backend}",
        "Use remote or ollama.",
    )

    if real_engine and backend == "remote":
        enabled = [
            item.strip().lower()
            for item in os.getenv(
                "AI_ENABLED_PROVIDERS", "gemini,groq"
            ).split(",")
            if item.strip()
        ]

        primary = os.getenv(
            "AI_PRIMARY_PROVIDER", "gemini"
        ).strip().lower()

        check(
            bool(enabled) and
            set(enabled).issubset({"gemini", "groq"}),
            "Supported remote AI providers configured",
            "Use gemini, groq, or both.",
        )

        check(
            primary in enabled,
            f"Primary AI provider: {primary}",
            "AI_PRIMARY_PROVIDER must be enabled.",
        )

        check(
            os.getenv(
                "ALLOW_PAID_PROVIDERS", "false"
            ).lower() not in {"true", "1", "yes"},
            "Paid providers disabled",
            "Set ALLOW_PAID_PROVIDERS=false.",
        )

        for provider in enabled:
            prefix = provider.upper()

            check(
                bool(os.getenv(f"{prefix}_API_KEY")),
                f"{provider} API key configured",
                f"Set {prefix}_API_KEY in .env.",
            )

            check(
                bool(os.getenv(f"{prefix}_MODEL")),
                f"{provider} model configured",
                f"Set {prefix}_MODEL in .env.",
            )

    if real_engine and backend == "ollama":
        check(
            bool(shutil.which("ollama")),
            "Ollama executable available",
            "Install Ollama or use the remote backend.",
        )

    if real_engine:
        check(
            bool(os.getenv("GITHUB_TOKEN")),
            "GitHub token configured",
            "Set GITHUB_TOKEN in .env.",
        )

        docker = shutil.which("docker")

        check(
            bool(docker),
            "Docker executable available",
            "Install Docker.",
        )

        if docker:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

            check(
                result.returncode == 0,
                "Docker daemon accessible",
                "Start Docker and verify your permissions.",
            )

            if result.returncode == 0:
                image = os.getenv(
                    "AUTORESOLVE_WORKER_IMAGE",
                    "autoresolve-test-worker:python312",
                )

                result = subprocess.run(
                    ["docker", "image", "inspect", image],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )

                check(
                    result.returncode == 0,
                    f"Docker worker image exists: {image}",
                    "Build the worker image using "
                    "docker/worker.Dockerfile.",
                )

    publish = os.getenv(
        "AUTORESOLVE_ENABLE_PUBLISH", "false"
    ).lower() in {"true", "1", "yes", "on"}

    merge = os.getenv(
        "AUTORESOLVE_ENABLE_MERGE", "false"
    ).lower() in {"true", "1", "yes", "on"}

    info(f"GitHub publishing: {publish}")
    info(f"GitHub merging: {merge}")

    if publish or merge:
        info(
            "WARNING: GitHub write operations are enabled. "
            "Use only a disposable test repository."
        )

    print()

    if failures:
        print(f"Setup check found {failures} issue(s).")
        return 1

    print("Setup checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

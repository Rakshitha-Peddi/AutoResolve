"""Checks that everything AutoResolve needs is set up, and says how to fix what isn't.

Run from the project folder:   python check_setup.py
Optionally test access to a repo:   python check_setup.py owner/repo
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OK, BAD, WARN = "  [ OK ]", "  [FAIL]", "  [warn]"
failures = 0


def report(ok, message, fix=""):
    global failures
    print(f"{OK if ok else BAD} {message}")
    if not ok:
        failures += 1
        if fix:
            print(f"         -> {fix}")


def main() -> int:
    repo_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    print("\nAutoResolve setup check\n")

    report(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}",
           "Install Python 3.10 or newer (3.12 recommended).")

    missing = []
    for module in ("fastapi", "uvicorn", "sqlalchemy", "dotenv", "github", "openai", "gspread"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    report(not missing, "Python packages installed" if not missing else f"Missing packages: {', '.join(missing)}",
           "Run: pip install -r requirements.txt")

    env_file = ROOT / ".env"
    report(env_file.exists(), ".env file found",
           "Run: cp .env.example .env   then open .env and fill in your keys.")
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    except ImportError:
        pass

    real = os.getenv("AUTORESOLVE_REAL_ENGINE", "false").lower() in {"1", "true", "yes", "on"}
    report(real, "AUTORESOLVE_REAL_ENGINE=true",
           "Without this AutoResolve runs the FAKE demo engine. Set it to true in .env.")

    # --- OpenAI
    key, model = os.getenv("OPENAI_API_KEY", ""), os.getenv("OPENAI_MODEL", "gpt-5.4")
    report(bool(key), "OPENAI_API_KEY is set", "Create a key at https://platform.openai.com/api-keys and put it in .env.")
    if key:
        try:
            from openai import OpenAI
            OpenAI(api_key=key).models.retrieve(model)
            report(True, f"OpenAI key works and model '{model}' is available")
        except Exception as exc:
            report(False, f"OpenAI check failed for model '{model}': {str(exc)[:160]}",
                   "Check the key, billing, and set OPENAI_MODEL in .env to a model your account lists.")

    # --- GitHub
    token = os.getenv("GITHUB_TOKEN", "")
    report(bool(token), "GITHUB_TOKEN is set", "Create a token (SETUP.md step 4) and put it in .env.")
    if token:
        try:
            from github import Github
            gh = Github(token)
            report(True, f"GitHub token works (user: {gh.get_user().login})")
            if repo_arg:
                repo = gh.get_repo(repo_arg)
                report(True, f"Can read repo {repo.full_name}")
                merge_on = os.getenv("AUTORESOLVE_ENABLE_MERGE", "false").lower() in {"1", "true", "yes", "on"}
                if merge_on:
                    report(bool(repo.permissions and repo.permissions.push),
                           "Token can push branches / open PRs (needed because AUTORESOLVE_ENABLE_MERGE=true)",
                           "Give the token 'Contents: Read and write' and 'Pull requests: Read and write' on this repo.")
                else:
                    print(f"{WARN} AUTORESOLVE_ENABLE_MERGE=false: read-only mode. Approve & Merge is off.")
        except Exception as exc:
            report(False, f"GitHub check failed: {str(exc)[:160]}", "Token is wrong, expired, or lacks access to the repo.")

    # --- Docker
    docker = subprocess.run(["docker", "info"], capture_output=True, text=True) if _has("docker") else None
    report(bool(docker and docker.returncode == 0), "Docker is installed and running",
           "Install Docker Desktop and START it (whale icon visible), then re-run.")
    if docker and docker.returncode == 0:
        image = os.getenv("AUTORESOLVE_WORKER_IMAGE", "autoresolve-test-worker:python312")
        found = subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0
        report(found, f"Docker test image '{image}' is built",
               "Run: docker build -f docker/worker.Dockerfile -t autoresolve-test-worker:python312 .")

    print()
    if failures:
        print(f"{failures} problem(s) to fix. Fix them top to bottom, then run this again.\n")
        return 1
    print("All good. Start the app with:  uvicorn backend.main:app --reload\n")
    return 0


def _has(cmd: str) -> bool:
    from shutil import which
    return which(cmd) is not None


if __name__ == "__main__":
    raise SystemExit(main())

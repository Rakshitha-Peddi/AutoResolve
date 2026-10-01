import subprocess
from pathlib import Path

class GitManager:
    def _run(self, args, cwd):
        return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()

    def ensure_repo(self, repo_path):
        p = Path(repo_path)
        if not (p / ".git").exists():
            self._run(["git", "init", "-b", "main"], p)
            self._run(["git", "config", "user.email", "autoresolve@example.com"], p)
            self._run(["git", "config", "user.name", "AutoResolve"], p)
            self._run(["git", "add", "."], p)
            self._run(["git", "commit", "-m", "chore: initialize demo repository"], p)

    def create_branch_commit(self, repo_path, bug_id, patch):
        p = Path(repo_path)
        self.ensure_repo(p)
        branch = f"autoresolve/BUG-{bug_id}"
        self._run(["git", "checkout", "-B", branch], p)
        self._run(["git", "add", "."], p)
        self._run(["git", "commit", "-m", f"fix(BUG-{bug_id}): automated repair"], p)
        return {"branch": branch, "commit": self._run(["git", "rev-parse", "HEAD"], p), "pr": f"mock://pull/{bug_id}"}

    def merge(self, repo_path, bug_id):
        p = Path(repo_path)
        self._run(["git", "checkout", "main"], p)
        branch = f"autoresolve/BUG-{bug_id}"
        self._run(["git", "merge", "--no-ff", branch, "-m", f"merge: AutoResolve BUG-{bug_id}"], p)
        return self._run(["git", "rev-parse", "HEAD"], p)

import subprocess
from pathlib import Path

class PatchApplier:
    def apply(self, repo_path, patch):
        if not patch:
            raise RuntimeError("AI produced an empty patch")
        p = Path(repo_path)
        result = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], input=patch, text=True, cwd=p, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Patch could not be applied")

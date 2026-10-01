import shutil
from pathlib import Path
import tempfile

class WorkspaceManager:
    def create(self, repo_path):
        root = Path(tempfile.mkdtemp(prefix="autoresolve-"))
        dest = root / "repo"
        shutil.copytree(repo_path, dest, dirs_exist_ok=True)
        return root, dest

    def destroy(self, root):
        shutil.rmtree(root, ignore_errors=True)

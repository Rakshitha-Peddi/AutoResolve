import subprocess
import sys

class TestRunner:
    def run(self, repo_path, timeout=30):
        result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=repo_path, text=True, capture_output=True, timeout=timeout)
        return {
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
        }

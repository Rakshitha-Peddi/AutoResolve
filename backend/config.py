import os
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))
EXECUTION_TIMEOUT_SECONDS = int(os.getenv("EXECUTION_TIMEOUT_SECONDS", "30"))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

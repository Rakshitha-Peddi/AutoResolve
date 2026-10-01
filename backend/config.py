"""Settings, read once from environment variables at import time."""
import os
from pathlib import Path

from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


DATABASE_URL: str = os.getenv("DATABASE_URL") or f"sqlite:///{PROJECT_ROOT / 'autoresolve.db'}"

# How many AI attempts a bug gets before it is marked "failed".
MAX_ITERATIONS: int = max(1, _int("MAX_ITERATIONS", 3))

# Google Sheets intake. Leave GOOGLE_SHEET_ID empty to switch it off.
GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SHEET_POLL_SECONDS: int = max(5, _int("SHEET_POLL_SECONDS", 60))

FRONTEND_DIR: Path = Path(os.getenv("FRONTEND_DIR") or PROJECT_ROOT / "frontend")

USE_REAL_ENGINE: bool = os.getenv(
    "AUTORESOLVE_REAL_ENGINE",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}

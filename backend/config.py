"""Settings, read once from environment variables at import time."""
import os
import re
from pathlib import Path

from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


DATABASE_URL: str = os.getenv("DATABASE_URL") or f"sqlite:///{PROJECT_ROOT / 'autoresolve.db'}"

# How many AI attempts a bug gets before it is marked "failed".
MAX_ITERATIONS: int = max(1, _int("MAX_ITERATIONS", 3))

# Google Sheets intake. Leave GOOGLE_SHEET_ID empty to switch it off.
# Google Sheets intake. Accept either a spreadsheet ID or its URL.
GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_URL: str = os.getenv("GOOGLE_SHEET_URL", "").strip()

if not GOOGLE_SHEET_ID and GOOGLE_SHEET_URL:
    match = re.search(
        r"/spreadsheets/d/([^/?#]+)",
        GOOGLE_SHEET_URL,
    )
    if match:
        GOOGLE_SHEET_ID = match.group(1)

# Resolve relative credential paths from the project root.
_credentials_path = Path(
    os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials/credentials.json")
).expanduser()

GOOGLE_CREDENTIALS_FILE: str = str(
    _credentials_path
    if _credentials_path.is_absolute()
    else PROJECT_ROOT / _credentials_path
)

OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.6").strip()
SHEET_POLL_SECONDS: int = max(5, _int("SHEET_POLL_SECONDS", 60))

FRONTEND_DIR: Path = Path(os.getenv("FRONTEND_DIR") or PROJECT_ROOT / "frontend")

USE_REAL_ENGINE: bool = os.getenv(
    "AUTORESOLVE_REAL_ENGINE",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}

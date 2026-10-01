"""Google Sheets intake: each new row in the sheet becomes a bug.

Expected headers in row 1: Title | Description | Repo | Reporter
(order does not matter; Repo and Reporter are optional).
"""
import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID
from backend.database.session import SessionLocal
from backend.models.bug import Bug
from backend.models.schemas import BugCreate
from backend.orchestrator import workflow

log = logging.getLogger("autoresolve.sheets")

DEFAULT_REPO = "default"


class SheetsError(Exception):
    pass


def is_enabled() -> bool:
    return bool(GOOGLE_SHEET_ID)


def _fetch_rows() -> list[list[str]]:
    """Every row of the first worksheet, header row included."""
    try:
        import gspread
    except ImportError as exc:
        raise SheetsError("gspread is not installed (pip install gspread)") from exc
    try:
        client = gspread.service_account(filename=GOOGLE_CREDENTIALS_FILE)
        return client.open_by_key(GOOGLE_SHEET_ID).sheet1.get_all_values()
    except Exception as exc:
        raise SheetsError(f"Could not read the sheet: {exc}") from exc


def sync_sheet() -> list[int]:
    """Create a bug for every row not seen before. Returns the new bug ids.

    This only creates the bugs (fast). The caller starts workflow.run_iteration()
    for each id, so a slow AI run never blocks the sheet check.
    """
    if not is_enabled():
        return []

    rows = _fetch_rows()
    if not rows:
        return []
    header = {name.strip().lower(): i for i, name in enumerate(rows[0])}
    if "title" not in header:
        raise SheetsError("Row 1 needs a 'Title' header (Title | Description | Repo | Reporter)")

    def cell(row: list[str], name: str) -> str:
        i = header.get(name)
        return row[i].strip() if i is not None and i < len(row) else ""

    created: list[int] = []
    with SessionLocal() as db:
        seen = set(db.scalars(select(Bug.source_ref).where(Bug.source == "sheet")))
        for row_number, row in enumerate(rows[1:], start=2):
            ref = f"{GOOGLE_SHEET_ID}:{row_number}"
            title = cell(row, "title")
            if ref in seen or not title:
                continue
            try:
                data = BugCreate(
                    title=title,
                    description=cell(row, "description") or title,
                    repo=cell(row, "repo") or DEFAULT_REPO,
                    reporter=cell(row, "reporter") or "unknown",
                )
                bug = workflow.create_bug(db, data, source="sheet", source_ref=ref)
            except ValidationError as exc:
                log.warning("Skipping sheet row %s: %s", row_number, exc.errors()[0]["msg"])
                continue
            except IntegrityError:  # another sync imported it first
                db.rollback()
                continue
            created.append(bug.id)
    if created:
        log.info("Imported %d new bug(s) from the sheet", len(created))
    return created

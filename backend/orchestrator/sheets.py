"""Google Sheets is the durable status ledger for sheet-originated bugs.

Required columns in the first worksheet (in this order):
A Title | B Description | C Repo | D Reporter | E Status | F Error

Only rows explicitly marked Pending are imported. Fixed and Failed rows are
never re-imported, including after loss of the local SQLite database.
"""

import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID
from backend.database.session import SessionLocal
from backend.models.bug import FAILED, MERGED, Bug
from backend.models.schemas import BugCreate
from backend.orchestrator import workflow

log = logging.getLogger("autoresolve.sheets")
DEFAULT_REPO = "default"
SHEET_HEADERS = ("title", "description", "repo", "reporter", "status", "error")
VALID_STATUSES = {"pending", "failed", "fixed"}


class SheetsError(Exception):
    """Google Sheets read or write could not be completed."""


def is_enabled() -> bool:
    return bool(GOOGLE_SHEET_ID)


def _worksheet():
    try:
        import gspread

        client = gspread.service_account(filename=GOOGLE_CREDENTIALS_FILE)
        return client.open_by_key(GOOGLE_SHEET_ID).sheet1
    except Exception as exc:
        raise SheetsError(f"Could not access Google Sheet: {exc}") from exc


def _fetch_rows() -> list[list[str]]:
    return _worksheet().get_all_values()


def _validated_rows(rows: list[list[str]]) -> list[list[str]]:
    if not rows:
        raise SheetsError("Google Sheet has no header row.")
    header = [value.strip().lower() for value in rows[0]]
    if header[:6] != list(SHEET_HEADERS):
        raise SheetsError(
            "Google Sheet columns A-F must be: "
            "Title, Description, Repo, Reporter, Status, Error"
        )
    return rows


def _source_row(bug: Bug) -> int | None:
    if bug.source != "sheet" or not bug.source_ref or not GOOGLE_SHEET_ID:
        return None
    sheet_id, sep, row_text = bug.source_ref.rpartition(":")
    if not sep or sheet_id != GOOGLE_SHEET_ID:
        return None
    try:
        row_number = int(row_text)
    except ValueError:
        return None
    return row_number if row_number >= 2 else None


def _matches_bug(row: list[str], bug: Bug) -> bool:
    # Avoid writing to a different report if somebody moved/deleted sheet rows.
    return (
        len(row) >= 1
        and row[0].strip() == bug.title
        and (len(row) < 3 or (row[2].strip() or DEFAULT_REPO) == bug.repo)
    )


def update_sheet_status(bug: Bug, status: str, error: str = "") -> bool:
    """Write E/F for a sheet bug. Return False for manually reported bugs.

    Raises SheetsError on write failures. A row-position mismatch is rejected
    instead of writing the wrong bug's status.
    """
    row_number = _source_row(bug)
    if row_number is None:
        return False
    if status not in ("Pending", "Failed", "Fixed"):
        raise ValueError("Invalid sheet status")
    try:
        ws = _worksheet()
        rows = _validated_rows(ws.get_all_values())
        if len(rows) < row_number or not _matches_bug(rows[row_number - 1], bug):
            raise SheetsError(
                f"Sheet row {row_number} moved or no longer matches {bug.public_id}; "
                "refusing to overwrite a different bug."
            )
        # E/F are updated as a single contiguous range.
        ws.update(
            range_name=f"E{row_number}:F{row_number}",
            values=[[status, str(error).strip()[:1500]]],
            value_input_option="RAW",
        )
        return True
    except SheetsError:
        raise
    except Exception as exc:
        raise SheetsError(f"Could not update sheet row {row_number}: {exc}") from exc


def record_sheet_result(bug: Bug, error: str = "") -> None:
    """Best-effort status write; failures remain visible in backend logs.

    Terminal statuses are retried by sync_sheet() on the next poll.
    """
    if bug.source != "sheet":
        return
    status = "Fixed" if bug.status == MERGED else "Failed" if bug.status == FAILED else "Pending"
    try:
        update_sheet_status(bug, status, error)
    except SheetsError:
        log.exception("Sheet status write-back failed for %s", bug.public_id)


def _terminal_error(bug: Bug) -> str:
    if bug.status == MERGED:
        return ""
    attempts = bug.attempts or []
    if attempts:
        last = attempts[-1].get("test_results") or {}
        detail = last.get("error") or last.get("stderr") or last.get("stdout")
        if detail:
            return str(detail).strip()[-1500:]
    return "Repair failed; inspect AutoResolve history for details."


def sync_sheet() -> list[int]:
    """Import only Pending rows and reconcile completed SQLite records.

    Reconciliation ensures a failed Sheets write doesn't lose the final state.
    This function does not start AI repairs; the caller schedules them.
    """
    if not is_enabled():
        return []

    rows = _validated_rows(_fetch_rows())
    created: list[int] = []
    with SessionLocal() as db:
        existing = {
            bug.source_ref: bug
            for bug in db.scalars(select(Bug).where(Bug.source == "sheet"))
        }
        for row_number, row in enumerate(rows[1:], start=2):
            title = row[0].strip() if row else ""
            state = row[4].strip().lower() if len(row) > 4 else ""
            ref = f"{GOOGLE_SHEET_ID}:{row_number}"
            if not title:
                continue
            if state not in VALID_STATUSES:
                log.warning("Skipping row %s: status must be Pending, Failed, or Fixed", row_number)
                continue

            bug = existing.get(ref)
            if bug:
                if not _matches_bug(row, bug):
                    log.warning("Sheet row %s changed identity; not updating", row_number)
                    continue
                desired = "Fixed" if bug.status == MERGED else "Failed" if bug.status == FAILED else None
                if desired and (state != desired.lower() or (desired == "Failed" and (len(row) < 6 or not row[5].strip()))):
                    # Retry terminal status writes that previously failed.
                    record_sheet_result(bug, _terminal_error(bug))
                continue

            # Crucial: even after SQLite deletion, Failed/Fixed are never imported.
            if state != "pending":
                continue
            try:
                data = BugCreate(
                    title=title,
                    description=row[1].strip() or title if len(row) > 1 else title,
                    repo=row[2].strip() or DEFAULT_REPO if len(row) > 2 else DEFAULT_REPO,
                    reporter=row[3].strip() or "unknown" if len(row) > 3 else "unknown",
                )
                bug = workflow.create_bug(db, data, source="sheet", source_ref=ref)
            except ValidationError as exc:
                reason = f"Invalid bug report: {exc.errors()[0]['msg']}"
                log.warning("Invalid sheet row %s: %s", row_number, reason)
                try:
                    ws = _worksheet()
                    latest = _validated_rows(ws.get_all_values())
                    if (len(latest) >= row_number
                            and latest[row_number - 1][:4] == row[:4]
                            and latest[row_number - 1][4].strip().lower() == "pending"):
                        ws.update(
                            range_name=f"E{row_number}:F{row_number}",
                            values=[["Failed", reason[:1500]]],
                            value_input_option="RAW",
                        )
                except Exception:
                    log.exception("Could not record invalid row %s", row_number)
                continue
            except IntegrityError:
                db.rollback()
                continue
            created.append(bug.id)
            existing[ref] = bug

    if created:
        log.info("Imported %d Pending bug(s) from Google Sheets", len(created))
    return created

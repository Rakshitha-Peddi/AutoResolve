"""Tests use fake worksheet; they never contact Google Sheets or AI providers."""
from unittest.mock import Mock

import pytest

from backend.database.session import Base, SessionLocal, engine
from backend.models.bug import FAILED, MERGED
from backend.models.schemas import BugCreate
from backend.orchestrator import sheets, workflow


@pytest.fixture()
def sheet_environment(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(sheets, "GOOGLE_SHEET_ID", "test-sheet-id")
    cells = [
        ["Title", "Description", "Repo", "Reporter", "Status", "Error"],
        ["Pending issue", "Something broke", "owner/repo", "Alice", "Pending", ""],
        ["Already fixed", "Resolved issue", "owner/repo", "Bob", "Fixed", ""],
        ["Already failed", "Unrecoverable", "owner/repo", "Cara", "Failed", "Some error"],
    ]
    ws = Mock()
    ws.get_all_values.side_effect = lambda: [list(row) for row in cells]

    def update(*, range_name, values, value_input_option):
        assert value_input_option == "RAW"
        assert range_name.startswith("E") and range_name.endswith(":F" + range_name.split(":")[0][1:])
        row_number = int(range_name.split(":")[0][1:])
        cells[row_number - 1][4:6] = values[0]

    ws.update.side_effect = update
    monkeypatch.setattr(sheets, "_worksheet", lambda: ws)
    monkeypatch.setattr(sheets, "_fetch_rows", ws.get_all_values)
    return ws, cells


def test_only_pending_imported_after_database_reset(sheet_environment):
    _, cells = sheet_environment
    assert len(sheets.sync_sheet()) == 1
    assert sheets.sync_sheet() == []
    with SessionLocal() as db:
        assert len(db.query(sheets.Bug).all()) == 1

    # After SQLite reset, Finished/Failed remain excluded by sheet status.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    assert len(sheets.sync_sheet()) == 1
    assert cells[2][4] == "Fixed"
    assert cells[3][4] == "Failed"


def test_sheet_writeback_fixed_only_after_merge(sheet_environment):
    _, cells = sheet_environment
    [bug_id] = sheets.sync_sheet()
    with SessionLocal() as db:
        bug = db.get(sheets.Bug, bug_id)
        sheets.record_sheet_result(bug)
        assert cells[1][4] == "Pending"
        bug.status = MERGED
        db.commit()
        sheets.record_sheet_result(bug)
        assert cells[1][4:6] == ["Fixed", ""]


def test_sheet_failure_writes_error(sheet_environment):
    _, cells = sheet_environment
    [bug_id] = sheets.sync_sheet()
    with SessionLocal() as db:
        bug = db.get(sheets.Bug, bug_id)
        bug.status = FAILED
        db.commit()
        sheets.record_sheet_result(bug, "Docker validation failed")
    assert cells[1][4:6] == ["Failed", "Docker validation failed"]


def test_non_sheet_bug_never_written(sheet_environment):
    ws, _ = sheet_environment
    with SessionLocal() as db:
        bug = workflow.create_bug(
            db,
            BugCreate(title="Manual issue", description="Broken", repo="owner/repo", reporter="Tester"),
        )
        sheets.record_sheet_result(bug, "anything")
    ws.update.assert_not_called()


def test_row_reordering_refuses_wrong_write(sheet_environment):
    _, cells = sheet_environment
    [bug_id] = sheets.sync_sheet()
    with SessionLocal() as db:
        bug = db.get(sheets.Bug, bug_id)
        cells[1][0] = "A different bug"
        with pytest.raises(sheets.SheetsError, match="no longer matches"):
            sheets.update_sheet_status(bug, "Fixed")

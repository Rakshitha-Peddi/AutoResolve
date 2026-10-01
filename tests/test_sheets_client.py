from unittest.mock import Mock, patch

from backend.orchestrator.sheets_client import GoogleSheetsClient


SHEET_URL = "https://docs.google.com/spreadsheets/d/test-sheet"


def create_client():
    fake_credentials = Mock()

    with patch(
        "backend.orchestrator.sheets_client.Credentials.from_service_account_file",
        return_value=fake_credentials,
    ), patch(
        "backend.orchestrator.sheets_client.gspread.authorize"
    ):
        return GoogleSheetsClient()


def test_google_sheet_access():
    client = create_client()

    fake_sheet = Mock()

    with patch.object(
        client,
        "open_sheet",
        return_value=fake_sheet,
    ):
        sheet = client.open_sheet(SHEET_URL)

    assert sheet is fake_sheet


def test_read_bugs():
    client = create_client()

    fake_worksheet = Mock()
    fake_worksheet.get_all_values.return_value = [
        ["Bug name", "Bug description", "RESOLVED OR NOT"],
        ["Test bug", "Something is broken", "NOT RESOLVED"],
    ]

    fake_sheet = Mock()
    fake_sheet.sheet1 = fake_worksheet

    with patch.object(
        client,
        "open_sheet",
        return_value=fake_sheet,
    ):
        bugs = client.get_bugs(SHEET_URL)

    assert len(bugs) == 1
    assert bugs[0]["bug_name"] == "Test bug"
    assert bugs[0]["description"] == "Something is broken"
    assert bugs[0]["status"] == "NOT RESOLVED"


def test_get_unresolved_bugs():
    client = create_client()

    fake_worksheet = Mock()
    fake_worksheet.get_all_values.return_value = [
        ["Bug name", "Bug description", "RESOLVED OR NOT"],
        ["Bug 1", "Still broken", "NOT RESOLVED"],
        ["Bug 2", "Already fixed", "RESOLVED"],
        ["Bug 3", "Already fixed", "YES"],
    ]

    fake_sheet = Mock()
    fake_sheet.sheet1 = fake_worksheet

    with patch.object(
        client,
        "open_sheet",
        return_value=fake_sheet,
    ):
        bugs = client.get_unresolved_bugs(SHEET_URL)

    assert len(bugs) == 1
    assert bugs[0]["bug_name"] == "Bug 1"
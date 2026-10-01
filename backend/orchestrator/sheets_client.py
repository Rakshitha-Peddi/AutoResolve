import os

import gspread
from google.oauth2.service_account import Credentials


class GoogleSheetsClient:
    """Google Sheets client for AutoResolve."""

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(self):
        credentials_path = os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_FILE",
            "credentials/google-service-account.json",
        )

        credentials = Credentials.from_service_account_file(
            credentials_path,
            scopes=self.SCOPES,
        )

        self.client = gspread.authorize(credentials)

    def open_sheet(self, sheet_url: str):
        return self.client.open_by_url(sheet_url)

    def get_bugs(self, sheet_url: str) -> list[dict]:
        sheet = self.open_sheet(sheet_url)
        worksheet = sheet.sheet1

        rows = worksheet.get_all_values()

        bugs = []

        for row in rows[1:]:
            if len(row) < 3:
                continue

            bug_name = row[0].strip()
            bug_description = row[1].strip()
            status = row[2].strip().upper()

            if not bug_name:
                continue

            bugs.append(
                {
                    "bug_name": bug_name,
                    "description": bug_description,
                    "status": status,
                }
            )

        return bugs

    def get_unresolved_bugs(self, sheet_url: str) -> list[dict]:
        bugs = self.get_bugs(sheet_url)

        return [
            bug
            for bug in bugs
            if bug["status"] not in {"RESOLVED", "YES"}
        ]
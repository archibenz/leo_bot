from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Sequence

import gspread  # type: ignore
from oauth2client.service_account import ServiceAccountCredentials  # type: ignore

REGISTRATIONS_SHEET = "Регистрации"
VISITS_SHEET = "Визиты"

REGISTRATIONS_HEADERS = [
    "Дата", "Имя", "Фамилия", "Username", "Telegram ID", "Телефон", "Источник",
]
VISITS_HEADERS = [
    "Дата", "Username", "Telegram ID", "Имя",
]


class GoogleSheetsClient:
    def __init__(self, sheet_id: str, credentials_file: Path):
        self.sheet_id = sheet_id
        self.credentials_file = credentials_file
        self._scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]

    def _client(self):
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            str(self.credentials_file), self._scope
        )
        return gspread.authorize(credentials)

    def _get_or_create_sheet(self, spreadsheet, title: str, headers: list[str]):
        try:
            ws = spreadsheet.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
            ws.append_row(headers)
        return ws

    def append_registration(self, values: Sequence[str]) -> None:
        spreadsheet = self._client().open_by_key(self.sheet_id)
        ws = self._get_or_create_sheet(spreadsheet, REGISTRATIONS_SHEET, REGISTRATIONS_HEADERS)
        ws.append_row(list(values))

    async def append_registration_async(self, values: Sequence[str]) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.append_registration, values)

    def record_visit(self, username: str, user_id: str, timestamp: str, first_name: str = "") -> None:
        spreadsheet = self._client().open_by_key(self.sheet_id)
        ws = self._get_or_create_sheet(spreadsheet, VISITS_SHEET, VISITS_HEADERS)
        ws.append_row([timestamp, username, user_id, first_name])

    async def record_visit_async(self, username: str, user_id: str, timestamp: str, first_name: str = "") -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.record_visit, username, user_id, timestamp, first_name)

    # Legacy — kept for compatibility
    def append_row(self, values: Sequence[str]) -> None:
        sheet = self._client().open_by_key(self.sheet_id).sheet1
        sheet.append_row(list(values))

    async def append_row_async(self, values: Sequence[str]) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.append_row, values)

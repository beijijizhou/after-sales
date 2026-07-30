import json
import os
import time
from urllib.parse import quote

import jwt
import requests


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


class GoogleSheetsClient:
    def __init__(self, service_account_info, timeout=30):
        self.info = dict(service_account_info)
        self.timeout = timeout
        self.session = requests.Session()
        self._access_token = None
        self._expires_at = 0

    @classmethod
    def from_environment(cls):
        raw = os.environ.get("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", "")
        if not raw:
            raise RuntimeError(
                "缺少 GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON"
            )
        return cls(json.loads(raw))

    def list_sheets(self, spreadsheet_id):
        payload = self._request(
            "GET",
            f"{SHEETS_API}/{spreadsheet_id}",
            params={
                "fields": (
                    "sheets.properties("
                    "sheetId,title,index,hidden,rowCount,columnCount)"
                )
            },
        )
        return [
            sheet["properties"] for sheet in payload.get("sheets", [])
        ]

    def batch_get_values(
        self, spreadsheet_id, ranges, value_render_option="UNFORMATTED_VALUE"
    ):
        if not ranges:
            return {}
        payload = self._request(
            "GET",
            f"{SHEETS_API}/{spreadsheet_id}/values:batchGet",
            params=[
                *[("ranges", cell_range) for cell_range in ranges],
                ("valueRenderOption", value_render_option),
            ],
        )
        return {
            item["range"]: item.get("values", [])
            for item in payload.get("valueRanges", [])
        }

    def update_values(
        self, spreadsheet_id, cell_range, values,
        value_input_option="USER_ENTERED",
    ):
        encoded_range = quote(cell_range, safe="")
        return self._request(
            "PUT",
            f"{SHEETS_API}/{spreadsheet_id}/values/{encoded_range}",
            params={"valueInputOption": value_input_option},
            json={"range": cell_range, "majorDimension": "ROWS", "values": values},
        )

    def _request(self, method, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._token()}"
        response = self.session.request(
            method, url, headers=headers, timeout=self.timeout, **kwargs
        )
        response.raise_for_status()
        return response.json()

    def _token(self):
        now = int(time.time())
        if self._access_token and now < self._expires_at - 60:
            return self._access_token
        assertion = jwt.encode(
            {
                "iss": self.info["client_email"],
                "scope": SHEETS_SCOPE,
                "aud": self.info.get(
                    "token_uri", "https://oauth2.googleapis.com/token"
                ),
                "iat": now,
                "exp": now + 3600,
            },
            self.info["private_key"],
            algorithm="RS256",
        )
        response = requests.post(
            self.info.get(
                "token_uri", "https://oauth2.googleapis.com/token"
            ),
            data={
                "grant_type": (
                    "urn:ietf:params:oauth:grant-type:jwt-bearer"
                ),
                "assertion": assertion,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        self._expires_at = now + int(payload.get("expires_in", 3600))
        return self._access_token

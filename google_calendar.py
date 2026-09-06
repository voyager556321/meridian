"""Google Calendar API client (incremental syncToken)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote

import requests

from auth import TokenProvider

CAL_BASE = "https://www.googleapis.com/calendar/v3"


class CalendarClient:
    def __init__(self, tokens: TokenProvider) -> None:
        self.tokens = tokens

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens.ensure()}"}

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        resp = requests.request(method, url, headers=self._headers(), timeout=60, **kwargs)
        if resp.status_code == 401:
            self.tokens.refresh()
            resp = requests.request(method, url, headers=self._headers(), timeout=60, **kwargs)
        return resp

    def list_calendars(self) -> list[dict[str, Any]]:
        resp = self._request("GET", f"{CAL_BASE}/users/me/calendarList")
        resp.raise_for_status()
        return list(resp.json().get("items") or [])

    def list_events_incremental(
        self,
        calendar_id: str,
        sync_token: str | None,
        *,
        on_page: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Return (events, next_sync_token). Raises GoneError on 410."""
        events: list[dict[str, Any]] = []
        page_token = None
        next_sync: str | None = None

        while True:
            params: dict[str, Any] = {
                "singleEvents": "true",
                "showDeleted": "true",
                "maxResults": 250,
            }
            if sync_token:
                params["syncToken"] = sync_token
            else:
                # Initial window: 30 days back, 90 forward
                now = datetime.now(timezone.utc)
                params["timeMin"] = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
                params["timeMax"] = (now + timedelta(days=90)).isoformat().replace("+00:00", "Z")
                params["orderBy"] = "startTime"
            if page_token:
                params["pageToken"] = page_token

            resp = self._request(
                "GET",
                f"{CAL_BASE}/calendars/{quote(calendar_id, safe='@')}/events",
                params=params,
            )
            if resp.status_code == 410:
                raise GoneError("calendar syncToken expired")
            resp.raise_for_status()
            data = resp.json()
            batch = list(data.get("items") or [])
            events.extend(batch)
            if on_page:
                on_page(batch)
            page_token = data.get("nextPageToken")
            if data.get("nextSyncToken"):
                next_sync = data["nextSyncToken"]
            if not page_token:
                break

        return events, next_sync or sync_token


class GoneError(Exception):
    pass

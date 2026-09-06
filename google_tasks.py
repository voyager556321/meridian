"""Google Tasks API client."""

from __future__ import annotations

from typing import Any

import requests

from auth import TokenProvider

TASKS_BASE = "https://tasks.googleapis.com/tasks/v1"


class TasksClient:
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

    def list_tasklists(self) -> list[dict[str, Any]]:
        resp = self._request("GET", f"{TASKS_BASE}/users/@me/lists")
        resp.raise_for_status()
        return list(resp.json().get("items") or [])

    def list_tasks(self, tasklist_id: str, show_completed: bool = False) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {
                "showCompleted": str(show_completed).lower(),
                "showHidden": "false",
                "maxResults": 100,
            }
            if page_token:
                params["pageToken"] = page_token
            resp = self._request(
                "GET",
                f"{TASKS_BASE}/lists/{tasklist_id}/tasks",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            tasks.extend(data.get("items") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return tasks

    def complete_task(self, tasklist_id: str, task_id: str) -> dict[str, Any]:
        resp = self._request(
            "PATCH",
            f"{TASKS_BASE}/lists/{tasklist_id}/tasks/{task_id}",
            json={"status": "completed"},
        )
        resp.raise_for_status()
        return resp.json()

    def reopen_task(self, tasklist_id: str, task_id: str) -> dict[str, Any]:
        resp = self._request(
            "PATCH",
            f"{TASKS_BASE}/lists/{tasklist_id}/tasks/{task_id}",
            json={"status": "needsAction"},
        )
        resp.raise_for_status()
        return resp.json()

    def create_task(
        self,
        tasklist_id: str,
        title: str,
        *,
        notes: str = "",
        due_iso: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title.strip()}
        if notes.strip():
            body["notes"] = notes.strip()
        if due_iso:
            # Tasks API expects RFC3339 date at midnight UTC often as ...T00:00:00.000Z
            body["due"] = due_iso
        resp = self._request(
            "POST",
            f"{TASKS_BASE}/lists/{tasklist_id}/tasks",
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

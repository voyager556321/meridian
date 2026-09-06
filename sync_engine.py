"""Background sync orchestration for Calendar + Tasks."""

from __future__ import annotations

import threading
import traceback
from datetime import datetime, timezone
from typing import Callable

from gi.repository import GLib

from auth import TokenProvider
from config import load_config
from db import (
    clear_events_for_account,
    default_tasklist_id,
    get_sync_state,
    init_db,
    set_calendar_sync_token,
    set_tasks_updated_min,
    today_events,
    today_tasks,
    touch_sync,
    update_task_status_local,
    upsert_account,
    upsert_calendar,
    upsert_event,
    upsert_task,
    upsert_tasklist,
)
from google_calendar import CalendarClient, GoneError
from google_tasks import TasksClient
from secrets_store import load_any_tokens

StatusCb = Callable[[str], None]
DataCb = Callable[[list[dict], list[dict], str | None], None]


def _friendly_api_error(exc: BaseException) -> str:
    text = str(exc)
    lower = text.lower()
    if "tasks.googleapis.com" in lower and ("403" in text or "forbidden" in lower):
        return (
            "Enable Google Tasks API in Cloud Console "
            "(apis/library/tasks.googleapis.com), then Sign out and Sign in again."
        )
    if "calendar" in lower and ("403" in text or "forbidden" in lower):
        return (
            "Enable Google Calendar API in Cloud Console, then Sign out / Sign in."
        )
    return text


class SyncEngine:
    def __init__(self) -> None:
        init_db()
        self._lock = threading.Lock()
        self._busy = False
        self._timer_id: int | None = None
        self._on_status: StatusCb | None = None
        self._on_data: DataCb | None = None
        self.email: str | None = None

    def set_callbacks(self, on_status: StatusCb | None = None, on_data: DataCb | None = None) -> None:
        self._on_status = on_status
        self._on_data = on_data

    def _emit_status(self, message: str) -> None:
        if self._on_status:
            GLib.idle_add(self._on_status, message, priority=GLib.PRIORITY_DEFAULT)

    def _emit_data(self, error: str | None = None) -> None:
        email = self.email
        events = today_events(email)
        tasks = today_tasks(email)
        if self._on_data:
            GLib.idle_add(self._on_data, events, tasks, error, priority=GLib.PRIORITY_DEFAULT)

    def load_cached(self) -> None:
        email, _tokens = load_any_tokens()
        self.email = email
        self._emit_data()

    def start_periodic(self) -> None:
        self.stop_periodic()
        interval = max(30, int(load_config().get("sync_interval_seconds", 90)))
        self._timer_id = GLib.timeout_add_seconds(interval, self._on_timer)

    def stop_periodic(self) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _on_timer(self) -> bool:
        self.sync_async()
        return True

    def sync_async(self, force: bool = False) -> None:
        with self._lock:
            if self._busy and not force:
                return
            self._busy = True
        threading.Thread(target=self._sync_worker, name="meridian-sync", daemon=True).start()

    def complete_task_async(self, tasklist_id: str, task_id: str, completed: bool) -> None:
        threading.Thread(
            target=self._complete_worker,
            args=(tasklist_id, task_id, completed),
            name="meridian-task",
            daemon=True,
        ).start()

    def create_task_async(self, title: str, notes: str = "") -> None:
        threading.Thread(
            target=self._create_task_worker,
            args=(title, notes),
            name="meridian-create-task",
            daemon=True,
        ).start()

    def _sync_worker(self) -> None:
        try:
            email, tokens = load_any_tokens()
            if not email or not tokens:
                self._emit_status("Not signed in")
                self._emit_data("Sign in to sync Google Calendar and Tasks")
                return

            self.email = email
            upsert_account(email)
            provider = TokenProvider(email)
            cal = CalendarClient(provider)
            tasks_api = TasksClient(provider)

            self._emit_status("Syncing calendars…")
            calendars = cal.list_calendars()
            for item in calendars:
                upsert_calendar(email, item)

            state = get_sync_state(email)
            sync_token = state.get("calendar_sync_token")

            primary = next((c for c in calendars if c.get("primary")), None)
            targets = [primary] if primary else calendars[:1]
            for item in calendars:
                if item.get("selected", True) and item not in targets:
                    targets.append(item)

            for idx, cal_item in enumerate(targets[:5]):
                if not cal_item:
                    continue
                cid = cal_item["id"]
                token = sync_token if idx == 0 else None
                try:
                    self._emit_status(f"Syncing {cal_item.get('summary') or cid}…")
                    events, new_token = cal.list_events_incremental(cid, token)
                    for ev in events:
                        upsert_event(email, cid, ev)
                    if idx == 0 and new_token:
                        set_calendar_sync_token(email, new_token)
                except GoneError:
                    if idx == 0:
                        set_calendar_sync_token(email, None)
                        clear_events_for_account(email)
                        events, new_token = cal.list_events_incremental(cid, None)
                        for ev in events:
                            upsert_event(email, cid, ev)
                        if new_token:
                            set_calendar_sync_token(email, new_token)
                    else:
                        events, _ = cal.list_events_incremental(cid, None)
                        for ev in events:
                            upsert_event(email, cid, ev)

            self._emit_status("Syncing tasks…")
            try:
                for tlist in tasks_api.list_tasklists():
                    upsert_tasklist(email, tlist)
                    for task in tasks_api.list_tasks(tlist["id"], show_completed=False):
                        upsert_task(email, tlist["id"], task)
                set_tasks_updated_min(email, datetime.now(timezone.utc).isoformat())
            except Exception as tasks_exc:  # noqa: BLE001
                traceback.print_exc()
                msg = f"Calendar OK · Tasks: {_friendly_api_error(tasks_exc)}"
                touch_sync(email)
                self._emit_status(msg)
                self._emit_data(msg)
                return

            touch_sync(email)
            self._emit_status("Synced")
            self._emit_data()
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            msg = _friendly_api_error(exc)
            self._emit_status(f"Sync failed: {msg}")
            self._emit_data(msg)
        finally:
            with self._lock:
                self._busy = False

    def _complete_worker(self, tasklist_id: str, task_id: str, completed: bool) -> None:
        try:
            email, _ = load_any_tokens()
            if not email:
                return
            provider = TokenProvider(email)
            api = TasksClient(provider)
            if completed:
                result = api.complete_task(tasklist_id, task_id)
                update_task_status_local(task_id, "completed", result.get("completed") or "")
            else:
                api.reopen_task(tasklist_id, task_id)
                update_task_status_local(task_id, "needsAction", "")
            self._emit_status("Task updated")
            self._emit_data()
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._emit_status(f"Task update failed: {_friendly_api_error(exc)}")
            self.sync_async(force=True)

    def _create_task_worker(self, title: str, notes: str) -> None:
        try:
            email, _ = load_any_tokens()
            if not email:
                self._emit_status("Not signed in")
                return
            self._emit_status("Creating task…")
            provider = TokenProvider(email)
            api = TasksClient(provider)
            tasklist_id = default_tasklist_id(email)
            if not tasklist_id:
                lists = api.list_tasklists()
                for tlist in lists:
                    upsert_tasklist(email, tlist)
                tasklist_id = lists[0]["id"] if lists else None
            if not tasklist_id:
                raise RuntimeError("No Google task list found")
            created = api.create_task(tasklist_id, title, notes=notes)
            upsert_task(email, tasklist_id, created)
            self._emit_status("Task created")
            self._emit_data()
            self.sync_async(force=True)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._emit_status(f"Create failed: {_friendly_api_error(exc)}")
            self._emit_data(_friendly_api_error(exc))

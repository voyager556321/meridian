"""SQLite cache for Meridian calendars, events, and tasks."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from typing import Any, Iterator

from config import DB_PATH, ensure_dirs


def _connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                email TEXT PRIMARY KEY,
                display_name TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS calendars (
                id TEXT PRIMARY KEY,
                account_email TEXT NOT NULL,
                summary TEXT,
                primary_cal INTEGER DEFAULT 0,
                background_color TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                calendar_id TEXT NOT NULL,
                account_email TEXT NOT NULL,
                summary TEXT,
                description TEXT,
                location TEXT,
                start_iso TEXT,
                end_iso TEXT,
                all_day INTEGER DEFAULT 0,
                status TEXT,
                updated_at TEXT,
                html_link TEXT
            );

            CREATE TABLE IF NOT EXISTS tasklists (
                id TEXT PRIMARY KEY,
                account_email TEXT NOT NULL,
                title TEXT
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                tasklist_id TEXT NOT NULL,
                account_email TEXT NOT NULL,
                title TEXT,
                notes TEXT,
                status TEXT,
                due_iso TEXT,
                updated_at TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                account_email TEXT PRIMARY KEY,
                calendar_sync_token TEXT,
                tasks_updated_min TEXT,
                last_sync_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_iso);
            CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_iso);
            """
        )
        cols = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
        if "html_link" not in cols:
            conn.execute("ALTER TABLE events ADD COLUMN html_link TEXT")


def upsert_account(email: str, display_name: str = "") -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO accounts(email, display_name, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                display_name=excluded.display_name,
                updated_at=excluded.updated_at
            """,
            (email.lower(), display_name, datetime.now(timezone.utc).isoformat()),
        )


def upsert_calendar(account_email: str, cal: dict[str, Any]) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO calendars(id, account_email, summary, primary_cal, background_color)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                summary=excluded.summary,
                primary_cal=excluded.primary_cal,
                background_color=excluded.background_color
            """,
            (
                cal["id"],
                account_email.lower(),
                cal.get("summary") or "",
                1 if cal.get("primary") else 0,
                cal.get("backgroundColor") or "",
            ),
        )


def upsert_event(account_email: str, calendar_id: str, event: dict[str, Any]) -> None:
    status = event.get("status") or "confirmed"
    if status == "cancelled":
        with db() as conn:
            conn.execute("DELETE FROM events WHERE id=?", (event["id"],))
        return

    start = event.get("start") or {}
    end = event.get("end") or {}
    all_day = "date" in start
    start_iso = start.get("dateTime") or start.get("date") or ""
    end_iso = end.get("dateTime") or end.get("date") or ""

    with db() as conn:
        conn.execute(
            """
            INSERT INTO events(
                id, calendar_id, account_email, summary, description, location,
                start_iso, end_iso, all_day, status, updated_at, html_link
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                calendar_id=excluded.calendar_id,
                summary=excluded.summary,
                description=excluded.description,
                location=excluded.location,
                start_iso=excluded.start_iso,
                end_iso=excluded.end_iso,
                all_day=excluded.all_day,
                status=excluded.status,
                updated_at=excluded.updated_at,
                html_link=excluded.html_link
            """,
            (
                event["id"],
                calendar_id,
                account_email.lower(),
                event.get("summary") or "(No title)",
                event.get("description") or "",
                event.get("location") or "",
                start_iso,
                end_iso,
                1 if all_day else 0,
                status,
                event.get("updated") or datetime.now(timezone.utc).isoformat(),
                event.get("htmlLink") or "",
            ),
        )


def clear_events_for_account(account_email: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM events WHERE account_email=?", (account_email.lower(),))


def upsert_tasklist(account_email: str, item: dict[str, Any]) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO tasklists(id, account_email, title)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title
            """,
            (item["id"], account_email.lower(), item.get("title") or "Tasks"),
        )


def upsert_task(account_email: str, tasklist_id: str, task: dict[str, Any]) -> None:
    if task.get("deleted"):
        with db() as conn:
            conn.execute("DELETE FROM tasks WHERE id=?", (task["id"],))
        return
    with db() as conn:
        conn.execute(
            """
            INSERT INTO tasks(
                id, tasklist_id, account_email, title, notes, status,
                due_iso, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tasklist_id=excluded.tasklist_id,
                title=excluded.title,
                notes=excluded.notes,
                status=excluded.status,
                due_iso=excluded.due_iso,
                updated_at=excluded.updated_at,
                completed_at=excluded.completed_at
            """,
            (
                task["id"],
                tasklist_id,
                account_email.lower(),
                task.get("title") or "",
                task.get("notes") or "",
                task.get("status") or "needsAction",
                task.get("due") or "",
                task.get("updated") or "",
                task.get("completed") or "",
            ),
        )


def get_sync_state(account_email: str) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM sync_state WHERE account_email=?",
            (account_email.lower(),),
        ).fetchone()
    if not row:
        return {
            "account_email": account_email.lower(),
            "calendar_sync_token": None,
            "tasks_updated_min": None,
            "last_sync_at": None,
        }
    return dict(row)


def set_calendar_sync_token(account_email: str, token: str | None) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO sync_state(account_email, calendar_sync_token, last_sync_at)
            VALUES (?, ?, ?)
            ON CONFLICT(account_email) DO UPDATE SET
                calendar_sync_token=excluded.calendar_sync_token,
                last_sync_at=excluded.last_sync_at
            """,
            (account_email.lower(), token, datetime.now(timezone.utc).isoformat()),
        )


def set_tasks_updated_min(account_email: str, value: str | None) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO sync_state(account_email, tasks_updated_min, last_sync_at)
            VALUES (?, ?, ?)
            ON CONFLICT(account_email) DO UPDATE SET
                tasks_updated_min=excluded.tasks_updated_min,
                last_sync_at=excluded.last_sync_at
            """,
            (account_email.lower(), value, datetime.now(timezone.utc).isoformat()),
        )


def touch_sync(account_email: str) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO sync_state(account_email, last_sync_at)
            VALUES (?, ?)
            ON CONFLICT(account_email) DO UPDATE SET last_sync_at=excluded.last_sync_at
            """,
            (account_email.lower(), datetime.now(timezone.utc).isoformat()),
        )


def _day_bounds_local(day: date) -> tuple[str, str]:
    start = datetime.combine(day, time.min).astimezone().isoformat()
    end = datetime.combine(day, time.max).astimezone().isoformat()
    # Also support all-day YYYY-MM-DD
    return start, end


def today_events(account_email: str | None = None, day: date | None = None) -> list[dict[str, Any]]:
    day = day or date.today()
    day_str = day.isoformat()
    start_bound, end_bound = _day_bounds_local(day)
    sql = """
        SELECT * FROM events
        WHERE status != 'cancelled'
          AND (
            (all_day = 1 AND start_iso <= ? AND (end_iso = '' OR end_iso > ?))
            OR (all_day = 0 AND start_iso < ? AND (end_iso = '' OR end_iso > ?))
          )
    """
    params: list[Any] = [day_str, day_str, end_bound, start_bound]
    if account_email:
        sql += " AND account_email = ?"
        params.append(account_email.lower())
    sql += " ORDER BY all_day DESC, start_iso ASC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def today_tasks(account_email: str | None = None, day: date | None = None) -> list[dict[str, Any]]:
    day = day or date.today()
    day_str = day.isoformat()
    # Include open tasks due today/overdue, plus undated open tasks
    sql = """
        SELECT * FROM tasks
        WHERE status = 'needsAction'
          AND (
            due_iso = '' OR due_iso IS NULL
            OR substr(due_iso, 1, 10) <= ?
          )
    """
    params: list[Any] = [day_str]
    if account_email:
        sql += " AND account_email = ?"
        params.append(account_email.lower())
    sql += " ORDER BY CASE WHEN due_iso IS NULL OR due_iso = '' THEN 1 ELSE 0 END, due_iso ASC, title ASC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def update_task_status_local(task_id: str, status: str, completed_at: str = "") -> None:
    with db() as conn:
        conn.execute(
            "UPDATE tasks SET status=?, completed_at=? WHERE id=?",
            (status, completed_at, task_id),
        )


def default_tasklist_id(account_email: str) -> str | None:
    with db() as conn:
        row = conn.execute(
            """
            SELECT id FROM tasklists
            WHERE account_email=?
            ORDER BY CASE WHEN lower(title)='my tasks' OR lower(title)='tasks' THEN 0 ELSE 1 END, title
            LIMIT 1
            """,
            (account_email.lower(),),
        ).fetchone()
    return row["id"] if row else None

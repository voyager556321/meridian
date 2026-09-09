"""GTK4 / Libadwaita Today UI for Meridian."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk

from config import (
    is_valid_client_id,
    load_config,
    oauth_ready_for_users,
    save_config,
    using_custom_oauth_client,
)
from oauth_defaults import has_bundled_client
from secrets_store import using_fallback_store

APP_VERSION = "0.1.0-mvp"


class SettingsDialog(Adw.PreferencesWindow):
    def __init__(self, parent: Gtk.Window, on_saved: Callable[[], None] | None = None) -> None:
        super().__init__(transient_for=parent, modal=True, search_enabled=False)
        self.set_title("Settings")
        self._on_saved = on_saved
        cfg = load_config()

        page = Adw.PreferencesPage(title="Preferences")

        sync_group = Adw.PreferencesGroup(title="Sync")
        self._interval = Adw.SpinRow(
            title="Sync interval",
            subtitle="Seconds between background syncs",
            adjustment=Gtk.Adjustment(
                value=float(cfg.get("sync_interval_seconds", 90)),
                lower=30,
                upper=3600,
                step_increment=30,
                page_increment=60,
            ),
        )
        sync_group.add(self._interval)
        page.add(sync_group)

        advanced = Adw.PreferencesGroup(
            title="Advanced",
            description=(
                "Optional. Leave empty to use Meridian’s built-in Google login. "
                "Only fill this if you bring your own Desktop OAuth client."
            ),
        )
        override_id = str(cfg.get("google_client_id", ""))
        if not is_valid_client_id(override_id):
            override_id = ""
        self._client_id = Adw.EntryRow(
            title="Custom Client ID",
            text=override_id,
        )
        self._client_secret = Adw.PasswordEntryRow(title="Custom Client secret")
        secret = str(cfg.get("google_client_secret", ""))
        if len(secret) >= 12 and not secret.startswith("YOUR_"):
            self._client_secret.set_text(secret)

        clear_btn = Gtk.Button(label="Use built-in login", halign=Gtk.Align.CENTER)
        clear_btn.add_css_class("flat")
        clear_btn.set_margin_top(8)
        clear_btn.connect("clicked", self._clear_override)

        advanced.add(self._client_id)
        advanced.add(self._client_secret)
        advanced.add(clear_btn)
        page.add(advanced)

        save_btn = Gtk.Button(label="Save", halign=Gtk.Align.CENTER)
        save_btn.add_css_class("suggested-action")
        save_btn.set_margin_top(18)
        save_btn.connect("clicked", self._save)
        actions = Adw.PreferencesGroup()
        actions.add(save_btn)
        page.add(actions)
        self.add(page)

    def _clear_override(self, *_args) -> None:
        self._client_id.set_text("")
        self._client_secret.set_text("")

    def _save(self, *_args) -> None:
        client_id = self._client_id.get_text().strip()
        if client_id and not is_valid_client_id(client_id):
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading="Invalid Client ID",
                body=(
                    "Leave the field empty for normal Sign in, or paste a Desktop "
                    "OAuth Client ID ending with .apps.googleusercontent.com "
                    "(not your Gmail address)."
                ),
            )
            dialog.add_response("ok", "OK")
            dialog.present()
            return
        cfg = load_config()
        cfg["google_client_id"] = client_id
        cfg["google_client_secret"] = self._client_secret.get_text().strip() if client_id else ""
        cfg["sync_interval_seconds"] = int(self._interval.get_value())
        save_config(cfg)
        if self._on_saved:
            self._on_saved()
        self.close()


def _format_event_when(event: dict[str, Any]) -> str:
    if event.get("all_day"):
        return "All day"
    start = event.get("start_iso") or ""
    try:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M")
    except ValueError:
        return start[:16] if start else ""


def _format_task_due(task: dict[str, Any]) -> str:
    due = task.get("due_iso") or ""
    if not due:
        return "No due date"
    return f"Due {due[:10]}"


def _event_url(event: dict[str, Any]) -> str:
    link = (event.get("html_link") or "").strip()
    if link:
        return link
    eid = quote(str(event.get("id") or ""), safe="")
    return f"https://calendar.google.com/calendar/r/eventedit/{eid}"


class MeridianWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        cfg = load_config()  # also sanitizes bad client ids
        w = int(cfg.get("window", {}).get("width", 920))
        h = int(cfg.get("window", {}).get("height", 700))
        super().__init__(application=app, title="Meridian", default_width=w, default_height=h)
        self.set_icon_name("meridian")

        self._sync = None
        self._account_email = cfg.get("account_email") or ""
        self._events: list[dict[str, Any]] = []
        self._tasks: list[dict[str, Any]] = []

        self._toast = Adw.ToastOverlay()
        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=160)
        self._toast.set_child(self._stack)
        self.set_content(self._toast)

        self._build_signed_out()
        self._build_today()
        self._install_actions()
        self.connect("close-request", self._on_close)

        if using_fallback_store():
            GLib.idle_add(
                lambda: self.show_toast("libsecret unavailable — tokens stored in a local fallback file")
                or False
            )

    def set_sync_engine(self, engine) -> None:
        self._sync = engine

    def _install_actions(self) -> None:
        for name, cb in (
            ("signin", lambda *_: self.start_signin()),
            ("sync", lambda *_: self._on_sync_clicked()),
            ("settings", lambda *_: self.open_settings()),
            ("signout", lambda *_: self.sign_out()),
            ("new-task", lambda *_: self.open_new_task()),
            ("about", lambda *_: self.open_about()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)

    def _build_signed_out(self) -> None:
        page = Adw.StatusPage(
            icon_name="x-office-calendar-symbolic",
            title="Meridian",
            description="Your Google Calendar and Tasks for today — in one place.",
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)

        signin = Gtk.Button(label="Sign in with Google", halign=Gtk.Align.CENTER)
        signin.add_css_class("suggested-action")
        signin.add_css_class("pill")
        signin.set_size_request(220, -1)
        signin.connect("clicked", lambda *_: self.start_signin())
        box.append(signin)

        # Maintainer-only hint when bundled OAuth is missing
        if not has_bundled_client() and not using_custom_oauth_client():
            hint = Gtk.Label(
                label="Developer: set BUNDLED_CLIENT_ID in oauth_defaults.py",
                wrap=True,
                justify=Gtk.Justification.CENTER,
            )
            hint.add_css_class("dim-label")
            hint.add_css_class("caption")
            hint.set_margin_top(8)
            box.append(hint)

        page.set_child(box)
        self._stack.add_named(page, "signed-out")

    def _build_today(self) -> None:
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self._title = Adw.WindowTitle(title="Today", subtitle="")
        header.set_title_widget(self._title)

        new_btn = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="New task (Ctrl+N)")
        new_btn.connect("clicked", lambda *_: self.open_new_task())
        header.pack_start(new_btn)

        sync_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Sync now")
        sync_btn.connect("clicked", lambda *_: self._on_sync_clicked())
        header.pack_end(sync_btn)

        menu = Gio.Menu()
        menu.append("New task", "win.new-task")
        menu.append("Sync now", "win.sync")
        menu.append("Settings", "win.settings")
        menu.append("About Meridian", "win.about")
        menu.append("Sign out", "win.signout")
        menu.append("Quit", "app.quit")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_btn)
        toolbar.add_top_bar(header)

        self._status = Gtk.Label(label="Ready", xalign=0)
        self._status.add_css_class("dim-label")
        self._status.add_css_class("caption")
        self._status.set_margin_start(14)
        self._status.set_margin_end(14)
        self._status.set_margin_top(4)
        self._status.set_margin_bottom(4)
        toolbar.add_bottom_bar(self._status)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_top(12)
        content.set_margin_bottom(24)
        content.set_margin_start(18)
        content.set_margin_end(18)

        events_label = Gtk.Label(label="Events", xalign=0)
        events_label.add_css_class("heading")
        self._events_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        tasks_label = Gtk.Label(label="Tasks", xalign=0)
        tasks_label.add_css_class("heading")
        self._tasks_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])

        content.append(events_label)
        content.append(self._events_list)
        content.append(tasks_label)
        content.append(self._tasks_list)
        scroll.set_child(Adw.Clamp(maximum_size=720, child=content))
        toolbar.set_content(scroll)
        self._stack.add_named(toolbar, "today")

    def show_signed_out(self) -> None:
        self._stack.set_visible_child_name("signed-out")

    def show_today(self, email: str = "") -> None:
        if email:
            self._account_email = email
        self._title.set_subtitle(self._account_email or "")
        self._stack.set_visible_child_name("today")

    def set_status(self, message: str) -> None:
        self._status.set_label(message)

    def show_toast(self, message: str) -> None:
        self._toast.add_toast(Adw.Toast(title=message, timeout=4))

    def set_today_data(
        self,
        events: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        error: str | None = None,
    ) -> None:
        self._events = events
        self._tasks = tasks
        self._render()
        if error:
            self.show_toast(error)
        if self._account_email or events or tasks:
            self.show_today(self._account_email)

    def _clear_list(self, listbox: Gtk.ListBox) -> None:
        child = listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            listbox.remove(child)
            child = nxt

    def _render(self) -> None:
        self._clear_list(self._events_list)
        self._clear_list(self._tasks_list)

        if not self._events:
            empty = Adw.ActionRow(title="No events today", sensitive=False)
            self._events_list.append(empty)
        else:
            for ev in self._events:
                row = Adw.ActionRow(
                    title=ev.get("summary") or "(No title)",
                    subtitle=ev.get("location") or "Open in Google Calendar",
                    activatable=True,
                )
                when = Gtk.Label(label=_format_event_when(ev))
                when.add_css_class("dim-label")
                when.set_valign(Gtk.Align.CENTER)
                row.add_prefix(when)
                open_icon = Gtk.Image.new_from_icon_name("adw-external-link-symbolic")
                open_icon.set_opacity(0.55)
                row.add_suffix(open_icon)
                row.connect("activated", self._on_event_activated, ev)
                self._events_list.append(row)

        if not self._tasks:
            empty = Adw.ActionRow(title="No open tasks", sensitive=False)
            self._tasks_list.append(empty)
        else:
            for task in self._tasks:
                row = Adw.ActionRow(
                    title=task.get("title") or "Untitled",
                    subtitle=_format_task_due(task),
                    activatable=True,
                )
                check = Gtk.CheckButton()
                check.set_valign(Gtk.Align.CENTER)
                check.connect("toggled", self._on_task_toggled, task)
                row.add_prefix(check)
                self._tasks_list.append(row)

    def _on_event_activated(self, _row: Adw.ActionRow, event: dict[str, Any]) -> None:
        url = _event_url(event)
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
        except Exception as exc:  # noqa: BLE001
            self.show_toast(f"Could not open calendar: {exc}")

    def _on_task_toggled(self, button: Gtk.CheckButton, task: dict[str, Any]) -> None:
        if not button.get_active() or not self._sync:
            return
        button.set_sensitive(False)
        self._sync.complete_task_async(task["tasklist_id"], task["id"], True)

    def open_new_task(self) -> None:
        if not self._account_email:
            self.show_toast("Sign in first")
            return
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="New task",
            body="Creates a task in your default Google Tasks list.",
        )
        entry = Gtk.Entry(placeholder_text="What needs doing?", activates_default=True)
        entry.set_margin_top(8)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("create", "Create")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("create")

        def on_response(_d: Adw.MessageDialog, response: str) -> None:
            if response != "create":
                return
            title = entry.get_text().strip()
            if not title:
                self.show_toast("Enter a task title")
                return
            if not self._sync:
                return
            self._sync.create_task_async(title)
            self.show_toast("Creating task…")

        dialog.connect("response", on_response)
        dialog.present()
        entry.grab_focus()

    def open_about(self) -> None:
        about = Adw.AboutWindow(
            transient_for=self,
            application_name="Meridian",
            application_icon="meridian",
            version=APP_VERSION,
            developer_name="Meridian",
            comments=(
                "Local-first Today hub for Google Calendar and Tasks.\n\n"
                "Free MVP: one Google account, Today view, sync, quick-add tasks.\n\n"
                "Meridian Pro (coming): multi-account, week view, licensing — "
                "the path to paid distribution."
            ),
            license_type=Gtk.License.GPL_3_0,
        )
        about.present()

    def start_signin(self) -> None:
        if not oauth_ready_for_users():
            self.show_toast(
                "App login is not set up yet — maintainer must fill oauth_defaults.py"
            )
            self.set_status("OAuth client missing in oauth_defaults.py")
            return
        self.set_status("Starting Google sign-in…")

        def worker() -> None:
            try:
                from auth import run_login_flow

                result = run_login_flow(on_status=lambda m: GLib.idle_add(self.set_status, m))
                GLib.idle_add(self._on_signed_in, result.email)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self.set_status, f"Sign-in failed: {exc}")
                GLib.idle_add(self.show_toast, str(exc))

        threading.Thread(target=worker, name="meridian-auth", daemon=True).start()

    def _on_signed_in(self, email: str) -> None:
        self._account_email = email
        self.show_today(email)
        self.show_toast(f"Signed in as {email}")
        if self._sync:
            self._sync.email = email
            self._sync.start_periodic()
            self._sync.sync_async(force=True)

    def _on_sync_clicked(self, *_args) -> None:
        if not self._sync:
            return
        self._sync.sync_async(force=True)

    def open_settings(self) -> None:
        SettingsDialog(self, on_saved=lambda: self.show_toast("Settings saved")).present()

    def sign_out(self) -> None:
        from secrets_store import clear_tokens

        email = self._account_email or load_config().get("account_email") or ""
        if email:
            clear_tokens(str(email))
        cfg = load_config()
        cfg["account_email"] = ""
        save_config(cfg)
        self._account_email = ""
        self._events = []
        self._tasks = []
        if self._sync:
            self._sync.stop_periodic()
            self._sync.email = None
        self.show_signed_out()
        self.set_status("Signed out")

    def _on_close(self, *_args) -> bool:
        cfg = load_config()
        cfg["window"] = {"width": self.get_width(), "height": self.get_height()}
        save_config(cfg)
        return False

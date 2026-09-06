#!/usr/bin/env python3
"""Meridian — GNOME Today hub for Google Calendar + Tasks."""

from __future__ import annotations

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk

from config import APP_ID, APP_NAME, ensure_dirs, load_config
from secrets_store import load_any_tokens
from sync_engine import SyncEngine
from ui import MeridianWindow


class MeridianApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window: MeridianWindow | None = None
        self.sync = SyncEngine()
        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])
        self.set_accels_for_action("win.sync", ["<primary>r"])
        self.set_accels_for_action("win.settings", ["<primary>comma"])
        self.set_accels_for_action("win.new-task", ["<primary>n"])

    def _on_activate(self, *_args) -> None:
        ensure_dirs()
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.DEFAULT)

        if self.window is None:
            self.window = MeridianWindow(self)
            self.window.set_sync_engine(self.sync)
            self.sync.set_callbacks(
                on_status=self.window.set_status,
                on_data=self.window.set_today_data,
            )

            email, tokens = load_any_tokens()
            cfg_email = str(load_config().get("account_email") or "")
            if email or (tokens and cfg_email):
                self.window.show_today(email or cfg_email)
                self.sync.load_cached()
                self.sync.start_periodic()
                self.sync.sync_async()
            else:
                self.window.show_signed_out()
                self.window.set_status("Ready — sign in to sync")

        self.window.present()

    def _on_shutdown(self, *_args) -> None:
        self.sync.stop_periodic()


def _register_icon_path() -> None:
    icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "icons")
    if not os.path.isdir(icon_dir):
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    Gtk.IconTheme.get_for_display(display).add_search_path(icon_dir)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = MeridianApp()
    app.connect("startup", lambda *_: _register_icon_path())
    return app.run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

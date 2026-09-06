"""XDG paths and non-secret configuration for Meridian."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from oauth_defaults import bundled_client_id, bundled_client_secret, has_bundled_client

APP_ID = "org.gnome.Meridian"
APP_NAME = "Meridian"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "meridian"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "meridian"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "meridian"

CONFIG_PATH = CONFIG_DIR / "config.json"
DB_PATH = DATA_DIR / "meridian.db"

DEFAULT_CONFIG: dict[str, Any] = {
    # Optional override; empty = use oauth_defaults.BUNDLED_*
    "google_client_id": "",
    "google_client_secret": "",
    "sync_interval_seconds": 90,
    "account_email": "",
    "window": {"width": 920, "height": 700},
}


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def is_valid_client_id(client_id: str) -> bool:
    cid = (client_id or "").strip()
    return bool(cid) and "apps.googleusercontent.com" in cid and "@" not in cid


def _sanitize_oauth_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Drop mistaken email / placeholder values from client id fields."""
    out = dict(data)
    cid = str(out.get("google_client_id", "")).strip()
    if cid and not is_valid_client_id(cid):
        out["google_client_id"] = ""
    secret = str(out.get("google_client_secret", "")).strip()
    # Reject tiny / placeholder secrets (e.g. typed junk)
    if secret and (secret.startswith("YOUR_") or len(secret) < 12):
        out["google_client_secret"] = ""
    return out


def load_config() -> dict[str, Any]:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return deepcopy(DEFAULT_CONFIG)
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_CONFIG)
    merged = deepcopy(DEFAULT_CONFIG)
    if isinstance(data, dict):
        merged.update(data)
        if isinstance(data.get("window"), dict):
            merged["window"] = {**DEFAULT_CONFIG["window"], **data["window"]}
    cleaned = _sanitize_oauth_fields(merged)
    # Persist cleanup so bad email-as-id does not stick around
    if cleaned.get("google_client_id") != merged.get("google_client_id") or cleaned.get(
        "google_client_secret"
    ) != merged.get("google_client_secret"):
        save_config(cleaned)
    return cleaned


def save_config(config: dict[str, Any]) -> None:
    ensure_dirs()
    payload = deepcopy(DEFAULT_CONFIG)
    payload.update(_sanitize_oauth_fields(config))
    if isinstance(config.get("window"), dict):
        payload["window"] = {**DEFAULT_CONFIG["window"], **config["window"]}
    tmp = CONFIG_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    os.chmod(tmp, 0o600)
    tmp.replace(CONFIG_PATH)


def get_oauth_credentials(config: dict[str, Any] | None = None) -> tuple[str, str]:
    """Return (client_id, client_secret). Prefer valid user override, else bundled."""
    cfg = config if config is not None else load_config()
    override_id = str(cfg.get("google_client_id", "")).strip()
    override_secret = str(cfg.get("google_client_secret", "")).strip()
    if is_valid_client_id(override_id):
        return override_id, override_secret
    return bundled_client_id(), bundled_client_secret()


def has_oauth_client(config: dict[str, Any] | None = None) -> bool:
    client_id, _secret = get_oauth_credentials(config)
    return is_valid_client_id(client_id)


def using_custom_oauth_client(config: dict[str, Any] | None = None) -> bool:
    cfg = config if config is not None else load_config()
    return is_valid_client_id(str(cfg.get("google_client_id", "")))


def oauth_ready_for_users() -> bool:
    """True when Sign in can work without asking the user for a Client ID."""
    return has_oauth_client()

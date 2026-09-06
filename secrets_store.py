"""Persist OAuth tokens via Freedesktop Secret Service (GNOME Keyring)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from config import CACHE_DIR, ensure_dirs

SCHEMA_NAME = "org.gnome.Meridian.oauth"
ATTR_PROVIDER = "provider"
ATTR_ACCOUNT = "account"
PROVIDER = "google"

# Dev fallback when libsecret is unavailable (explicitly insecure)
_FALLBACK_PATH = CACHE_DIR / "oauth_tokens.json"


def _secret_available():
    try:
        import gi

        gi.require_version("Secret", "1")
        from gi.repository import Secret  # noqa: F401

        return True
    except Exception:
        return False


def _schema():
    from gi.repository import Secret

    return Secret.Schema.new(
        SCHEMA_NAME,
        Secret.SchemaFlags.NONE,
        {
            ATTR_PROVIDER: Secret.SchemaAttributeType.STRING,
            ATTR_ACCOUNT: Secret.SchemaAttributeType.STRING,
        },
    )


def save_tokens(account_email: str, payload: dict[str, Any]) -> None:
    ensure_dirs()
    account = account_email.strip().lower() or "default"
    blob = json.dumps(payload)

    if _secret_available():
        from gi.repository import Secret

        Secret.password_store_sync(
            _schema(),
            {ATTR_PROVIDER: PROVIDER, ATTR_ACCOUNT: account},
            Secret.COLLECTION_DEFAULT,
            f"Meridian Google ({account})",
            blob,
            None,
        )
        return

    # Fallback for headless/dev — warn via file mode 0600
    data = {}
    if _FALLBACK_PATH.exists():
        try:
            data = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    data[account] = payload
    tmp = _FALLBACK_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(_FALLBACK_PATH)


def load_tokens(account_email: str | None = None) -> dict[str, Any] | None:
    ensure_dirs()
    account = (account_email or "").strip().lower()

    if _secret_available():
        from gi.repository import Secret

        if account:
            raw = Secret.password_lookup_sync(
                _schema(),
                {ATTR_PROVIDER: PROVIDER, ATTR_ACCOUNT: account},
                None,
            )
            if not raw:
                return None
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None

        # No account hint: search any Meridian google secret via fallback file only
        # (Secret Service search API is awkward without libsecret collection iterate)
        pass

    if not _FALLBACK_PATH.exists():
        return None
    try:
        data = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if account and account in data:
        return data[account]
    if len(data) == 1:
        return next(iter(data.values()))
    # Prefer last written
    return data.get(account) if account else (next(iter(data.values())) if data else None)


def load_any_tokens() -> tuple[str | None, dict[str, Any] | None]:
    """Return (account_email, payload) for the first available session."""
    if _secret_available():
        # Try common path: fallback file mirrors account keys; also try empty lookup
        if _FALLBACK_PATH.exists():
            try:
                data = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data:
                    email = next(iter(data.keys()))
                    return email, data[email]
            except (OSError, json.JSONDecodeError):
                pass
        # Attempt lookup with account stored in config preference
        from config import load_config

        email = str(load_config().get("account_email", "")).strip().lower()
        if email:
            tokens = load_tokens(email)
            if tokens:
                return email, tokens
        return None, None

    if not _FALLBACK_PATH.exists():
        return None, None
    try:
        data = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    if not isinstance(data, dict) or not data:
        return None, None
    email = next(iter(data.keys()))
    return email, data[email]


def clear_tokens(account_email: str) -> None:
    account = account_email.strip().lower()
    if _secret_available():
        from gi.repository import Secret

        Secret.password_clear_sync(
            _schema(),
            {ATTR_PROVIDER: PROVIDER, ATTR_ACCOUNT: account},
            None,
        )
    if _FALLBACK_PATH.exists():
        try:
            data = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict) and account in data:
            del data[account]
            _FALLBACK_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            os.chmod(_FALLBACK_PATH, 0o600)


def using_fallback_store() -> bool:
    return not _secret_available()

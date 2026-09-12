"""Bundled Google OAuth Desktop client for Meridian.

Public git must NOT contain real client secrets.

Resolution order for (client_id, client_secret):
  1. Environment: MERIDIAN_GOOGLE_CLIENT_ID / MERIDIAN_GOOGLE_CLIENT_SECRET
  2. Local override file oauth_defaults.local.py (gitignored) — for maintainers
  3. Placeholders below (empty) — public clone without Sign-in until configured

Packaged releases inject credentials at build time from oauth_defaults.local.py
into the install tree (desktop OAuth secrets are extractable from binaries anyway).

Maintainer setup:
  1. Google Cloud Console → Desktop OAuth client
  2. cp oauth_defaults.local.py.example oauth_defaults.local.py
  3. Paste Client ID + secret into the local file (chmod 600)
  4. Optional: rotate secret in Google Cloud if it was ever committed/pushed
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

# Public placeholders — keep empty in git.
BUNDLED_CLIENT_ID = ""
BUNDLED_CLIENT_SECRET = ""


def _from_local_file() -> tuple[str, str]:
    path = Path(__file__).resolve().parent / "oauth_defaults.local.py"
    if not path.is_file():
        return "", ""
    spec = importlib.util.spec_from_file_location("oauth_defaults_local", path)
    if spec is None or spec.loader is None:
        return "", ""
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return (
        str(getattr(mod, "BUNDLED_CLIENT_ID", "") or "").strip(),
        str(getattr(mod, "BUNDLED_CLIENT_SECRET", "") or "").strip(),
    )


def _from_env() -> tuple[str, str]:
    return (
        (os.environ.get("MERIDIAN_GOOGLE_CLIENT_ID") or "").strip(),
        (os.environ.get("MERIDIAN_GOOGLE_CLIENT_SECRET") or "").strip(),
    )


def bundled_client_id() -> str:
    env_id, _ = _from_env()
    if env_id:
        return env_id
    local_id, _ = _from_local_file()
    if local_id:
        return local_id
    return (BUNDLED_CLIENT_ID or "").strip()


def bundled_client_secret() -> str:
    _, env_secret = _from_env()
    if env_secret:
        return env_secret
    _, local_secret = _from_local_file()
    if local_secret:
        return local_secret
    return (BUNDLED_CLIENT_SECRET or "").strip()


def has_bundled_client() -> bool:
    cid = bundled_client_id()
    return bool(cid) and "apps.googleusercontent.com" in cid and "@" not in cid

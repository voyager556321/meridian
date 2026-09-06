"""Bundled Google OAuth Desktop client for Meridian.

End users never see these fields — they only click "Sign in with Google".

Maintainer setup (once):
  1. Google Cloud Console → create project "Meridian"
  2. Enable Calendar API + Tasks API
  3. OAuth consent screen → External → add test users while in Testing
  4. Credentials → Create OAuth client → type **Desktop app**
  5. Paste Client ID and Client secret below

Do NOT commit real secrets to a public repo without accepting they are
extractable from the Flatpak/desktop binary (standard for installed apps).
"""

from __future__ import annotations

# Paste your Desktop OAuth client here (maintainer only):
BUNDLED_CLIENT_ID = "269086083919-vg5bo48vdo987vc7vr6dfvruskffcdnr.apps.googleusercontent.com"
BUNDLED_CLIENT_SECRET = "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"


def bundled_client_id() -> str:
    return (BUNDLED_CLIENT_ID or "").strip()


def bundled_client_secret() -> str:
    return (BUNDLED_CLIENT_SECRET or "").strip()


def has_bundled_client() -> bool:
    cid = bundled_client_id()
    return bool(cid) and "apps.googleusercontent.com" in cid and "@" not in cid

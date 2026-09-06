"""Google OAuth 2.0 for desktop: system browser + localhost PKCE."""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

import requests

from config import get_oauth_credentials, has_oauth_client, load_config, save_config
from secrets_store import save_tokens

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
USERINFO_URI = "https://www.googleapis.com/oauth2/v3/userinfo"

SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]


@dataclass
class AuthResult:
    email: str
    access_token: str
    refresh_token: str | None
    expires_in: int


class _OAuthHandler(BaseHTTPRequestHandler):
    server_version = "MeridianOAuth/1.0"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.rstrip("/") != "/oauth/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        qs = urllib.parse.parse_qs(parsed.query)
        self.server.result_query = {k: v[0] for k, v in qs.items() if v}  # type: ignore[attr-defined]
        self.server.event.set()  # type: ignore[attr-defined]

        body = (
            b"<html><body style='font-family:sans-serif;padding:2rem'>"
            b"<h1>Meridian</h1><p>Signed in. You can close this tab.</p>"
            b"</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def refresh_access_token(refresh_token: str) -> dict:
    client_id, client_secret = get_oauth_credentials()
    data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret
    resp = requests.post(TOKEN_URI, data=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_userinfo(access_token: str) -> dict:
    resp = requests.get(
        USERINFO_URI,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def run_login_flow(
    *,
    on_status: Callable[[str], None] | None = None,
) -> AuthResult:
    """Block until browser OAuth completes. Call from a worker thread."""
    cfg = load_config()
    if not has_oauth_client(cfg):
        raise RuntimeError(
            "Meridian is not configured with a Google OAuth client yet. "
            "The app maintainer must set BUNDLED_CLIENT_ID in oauth_defaults.py."
        )

    client_id, client_secret = get_oauth_credentials(cfg)
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)

    server = HTTPServer(("127.0.0.1", 0), _OAuthHandler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/oauth/callback"
    server.event = threading.Event()  # type: ignore[attr-defined]
    server.result_query = {}  # type: ignore[attr-defined]

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    url = f"{AUTH_URI}?{urllib.parse.urlencode(params)}"
    if on_status:
        on_status("Opening browser for Google sign-in…")
    webbrowser.open(url)

    if not server.event.wait(timeout=300):  # type: ignore[attr-defined]
        server.server_close()
        raise TimeoutError("OAuth timed out — try again")

    query = getattr(server, "result_query", {})
    server.server_close()

    if query.get("error"):
        raise RuntimeError(f"Google auth error: {query.get('error')}")
    if query.get("state") != state:
        raise RuntimeError("OAuth state mismatch")
    code = query.get("code")
    if not code:
        raise RuntimeError("No authorization code returned")

    if on_status:
        on_status("Exchanging authorization code…")

    token_data = {
        "client_id": client_id,
        "code": code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        token_data["client_secret"] = client_secret

    resp = requests.post(TOKEN_URI, data=token_data, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Token exchange failed: {resp.status_code} {resp.text[:300]}")
    tokens = resp.json()
    access = tokens.get("access_token")
    if not access:
        raise RuntimeError("No access_token in response")

    info = fetch_userinfo(access)
    email = str(info.get("email") or "unknown@google").lower()
    refresh = tokens.get("refresh_token")
    expires_in = int(tokens.get("expires_in") or 3600)

    payload = {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": expires_in,
        "token_type": tokens.get("token_type", "Bearer"),
        "scope": tokens.get("scope", " ".join(SCOPES)),
    }
    # Preserve previous refresh if Google omitted it on re-consent
    if not refresh:
        from secrets_store import load_tokens

        prev = load_tokens(email)
        if prev and prev.get("refresh_token"):
            payload["refresh_token"] = prev["refresh_token"]
            refresh = prev["refresh_token"]

    save_tokens(email, payload)
    cfg = load_config()
    cfg["account_email"] = email
    save_config(cfg)

    if on_status:
        on_status(f"Signed in as {email}")

    return AuthResult(
        email=email,
        access_token=access,
        refresh_token=refresh,
        expires_in=expires_in,
    )


class TokenProvider:
    """Loads/refreshes access tokens for API clients."""

    def __init__(self, email: str | None = None) -> None:
        self.email = (email or "").lower() or None
        self._access: str | None = None
        self._refresh: str | None = None

    def ensure(self) -> str:
        from secrets_store import load_any_tokens, load_tokens

        if self.email:
            data = load_tokens(self.email)
        else:
            self.email, data = load_any_tokens()
        if not data:
            raise RuntimeError("Not signed in")
        if not self.email:
            raise RuntimeError("No account email")

        self._refresh = data.get("refresh_token")
        self._access = data.get("access_token")
        if self._access:
            return self._access
        if not self._refresh:
            raise RuntimeError("Missing refresh token — sign in again")
        return self.refresh()

    def refresh(self) -> str:
        if not self._refresh:
            self.ensure()
        if not self._refresh:
            raise RuntimeError("Missing refresh token")
        tokens = refresh_access_token(self._refresh)
        self._access = tokens["access_token"]
        payload = {
            "access_token": self._access,
            "refresh_token": self._refresh,
            "expires_in": int(tokens.get("expires_in") or 3600),
            "token_type": tokens.get("token_type", "Bearer"),
            "scope": tokens.get("scope", ""),
        }
        save_tokens(self.email or "default", payload)
        return self._access

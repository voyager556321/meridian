# Meridian — Production Architecture Spec

**Working title:** Meridian  
**Target:** GNOME desktop · GTK4 · Libadwaita · Flatpak/Flathub  
**Problem:** Fragile GOA Google integration; no first-class Calendar+Tasks hub; Drive mounting removed/unstable.

This document is the design authority for MVP. Interactive summary: open the Cursor canvas `meridian-architecture`.

---

## 1. Product concept & value proposition

### Name
**Meridian** — the line through your day: calendar blocks and tasks on one Adwaita surface.

### Positioning
Not another “Drive mounter.” Not a GOA wrapper. A dedicated GTD/agenda client that owns its OAuth session, caches offline, and treats Google Drive as **attachments**, not a filesystem.

### MVP feature list
| Priority | Feature |
|----------|---------|
| P0 | System-browser OAuth (PKCE + localhost), tokens in libsecret |
| P0 | Today view: timed events + due/overdue tasks in one scroll |
| P0 | Calendar list/week; create/edit/delete events |
| P0 | Tasks: lists, due dates, complete/reopen, notes |
| P0 | SQLite local cache; optimistic UI; sync status |
| P1 | Contextual Drive: attach file(s) to a task (fileId + webViewLink) |
| P1 | Flatpak + Flathub metainfo; BYO OAuth client wizard |
| P2 | Optional HTTPS Push Bridge for Calendar watch channels |
| P2 | GNOME Shell search provider / Quick Settings tile |

### Contextual Google Drive (not FUSE)
1. Scope narrowly: prefer `https://www.googleapis.com/auth/drive.file`.
2. UX: “Attach from Drive…” → Google Picker **or** native file chooser that opens Drive web → paste link → resolve metadata via Files.get.
3. Persist on the task entity:
   ```json
   "drive_attachments": [
     {"id": "...", "name": "Q3 Plan", "mimeType": "application/vnd.google-apps.spreadsheet", "webViewLink": "https://..."}
   ]
   ```
4. Open with `gtk::show_uri_full` / `xdg-open`. No `google-drive-ocamlfuse`, no GVfs volume.

---

## 2. Sync & authentication engine

### 2.1 OAuth 2.0 without WebKitGTK
Google’s embedded WebView policies break constantly. Use the **installed-app / desktop** pattern:

1. Create OAuth client type **Desktop app** in Google Cloud Console.
2. Generate PKCE `code_verifier` / S256 `code_challenge` and random `state`.
3. Bind an ephemeral loopback server: `http://127.0.0.1:<port>/oauth/callback`.
4. Open the authorize URL in the **default system browser** (`gtk::show_uri` / portal).
5. On redirect, validate `state`, exchange `code` + verifier at `https://oauth2.googleapis.com/token`.
6. Persist `refresh_token` (+ access token expiry) via Secret Service; tear down the listener.

Required params: `access_type=offline`, and on first link `prompt=consent` so a refresh token is actually issued.

Scopes (MVP):
- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/tasks`
- `https://www.googleapis.com/auth/drive.file`
- `openid email` (account label in UI)

### 2.2 Sync: push vs poll (be honest)
**Calendar push** (`events.watch`) needs a public **HTTPS** `address`. A Flatpak on localhost cannot receive Google’s POST callbacks directly.

**Recommended hybrid**
| Mode | Mechanism | When |
|------|-----------|------|
| Default | Calendar `syncToken` incremental sync; Tasks list/`updatedMin` | Always |
| Adaptive poll | 45–90s while window focused; 5–15 min idle; pause on suspend (`login1`) | Default |
| Push Bridge (optional) | Tiny HTTPS relay registers watch channels, notifies app via WebSocket/SSE | Power users / self-host |

Channel lifecycle: renew before ~7 days; on `410 Gone`, clear syncToken and full resync.

**Tasks API:** no Calendar-style watch. Use etags / updated timestamps + the same adaptive scheduler.

### 2.3 Token storage (Freedesktop Secret Service)
- Crate/bindings: `secret-service` (Rust) or `libsecret` via GI (Python).
- Schema example: `org.gnome.Meridian.oauth` with attributes `{ "provider": "google", "account": "<email>" }`.
- Store JSON blob: `{ "refresh_token", "access_token", "expiry", "client_id_ref" }`.
- Never write refresh tokens to `~/.config` plaintext. Config may hold non-secret prefs only.

---

## 3. Tech stack evaluation

| Criterion | Rust (`gtk4-rs` + `libadwaita-rs`) | Python (PyGObject) |
|-----------|-------------------------------------|--------------------|
| Async Google I/O | Excellent (`tokio`, `reqwest`, `oauth2`); bridge to GLib main context via channels / `glib::spawn_future_local` | Good enough (`asyncio`, threads + `GLib.idle_add`) but easier to stall UI if careless |
| Memory / battery | Clear winner for always-resident sync | Higher baseline |
| UI iteration speed | Slower | Faster |
| Flatpak | First-class Rust SDK extension | Larger runtime; GI packaging footguns |
| Ecosystem | `sqlx`/`rusqlite`, `keyring`/`secret-service` | Mature Google client libs |

### Recommendation
**Production: Rust.** Prototype UI in Python only as a disposable spike—do not ship both.

### Directory structure
```text
meridian/
  crates/
    meridian-app/       # Adw.Application, pages, widgets
    meridian-core/      # SyncEngine, domain models, commands
    meridian-google/    # OAuth loopback, Calendar/Tasks/Drive REST
    meridian-db/        # SQLite migrations + repositories
    meridian-secrets/   # Secret Service
  flatpak/org.gnome.Meridian.json
  data/icons/…  data/org.gnome.Meridian.desktop  data/org.gnome.Meridian.metainfo.xml
```

Separation of concerns: UI never talks HTTP; it dispatches commands to `SyncEngine`, which reads/writes SQLite and calls `meridian-google`.

---

## 4. Rate limits & Flathub distribution

Shared client IDs on Flathub are **public** and quota-shared.

| Strategy | Description | Verdict |
|----------|-------------|---------|
| **A. BYO credentials** | First-run: user creates GCP OAuth Desktop client, pastes Client ID (and secret if issued) into libsecret | **Primary** for full read/write |
| **B. Shared app client** | Ship Meridian’s client ID; aggressive syncToken/cache; 429 backoff | OK for limited demo / read-only |
| **C. Auth proxy** | Worker exchanges codes, enforces per-user rate limits | Only if you accept operating a backend + privacy policy |

**Shipping policy:** demo mode (B, read-heavy, cached) → unlock write scopes only after BYO client (A). Document a 5-minute GCP setup. Assume any embedded secret is extractable from the Flatpak.

---

## 5. Security & privacy notes
- Prefer PKCE; treat desktop client secret as non-confidential.
- CSRF `state` binding to the loopback session.
- Clear Secret Service entries on “Sign out”.
- Minimal scopes; justify Drive as attachments-only in consent screen.
- Flatpak portals: OpenURI for browser; no unnecessary home access beyond XDG config/cache.

---

## 6. Implementation sequence
1. Adw shell + Today empty state  
2. AuthManager loopback + libsecret  
3. SQLite schema (accounts, calendars, events, tasklists, tasks, attachments)  
4. Calendar incremental sync  
5. Tasks sync + Today merge  
6. Drive attach flow  
7. Flatpak + BYO OAuth wizard  
8. Optional Push Bridge  

Boilerplate for the async app entrypoint lives in `docs/meridian_bootstrap.rs` (recommended stack).

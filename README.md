# Meridian

Local-first GNOME agenda: **Google Calendar + Tasks** in one Libadwaita window.
One-click **Sign in with Google** — end users never touch Google Cloud Console.

**Status: MVP (0.1.0)** — enough to dogfood, share with early users, then sell Pro.

## MVP includes

- Sign in with Google (browser OAuth + libsecret tokens)
- Today view: events + open tasks
- Background sync (Calendar `syncToken` + Tasks)
- Complete tasks and **quick-add** (`Ctrl+N`)
- Click an event → open in Google Calendar
- Settings (sync interval; optional custom OAuth client)
- About teaser for **Meridian Pro** (multi-account / paid path)

## For end users

```bash
./meridian
# or after install:
./scripts/install.sh
meridian
```

Click **Sign in with Google** → approve in the browser → Today fills in.

---

## For the Meridian maintainer (once)

1. [Google Cloud Console](https://console.cloud.google.com/) → project `Meridian`
2. Enable **Google Calendar API** and **Google Tasks API**
3. OAuth consent → External → add test users while in Testing
4. Credentials → OAuth client → **Desktop app**
5. Set in [`oauth_defaults.py`](oauth_defaults.py):

```python
BUNDLED_CLIENT_ID = "123456789-xxxx.apps.googleusercontent.com"
BUNDLED_CLIENT_SECRET = "GOCSPX-xxxx"
```

6. Restart Meridian.

---

## Install (Arch)

```bash
sudo pacman -S --needed python python-pip python-gobject gtk4 libadwaita \
  gobject-introspection libsecret python-virtualenv

cd /path/to/meridian
virtualenv --python=/usr/bin/python3 --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
# edit oauth_defaults.py (maintainer)
./meridian
# optional user install:
./scripts/install.sh
```

## Next: promote & monetize

MVP is the free core. Revenue focus after dogfooding:

1. **Distribution** — Flathub / AUR / GitHub Releases; short demo GIF + landing page
2. **OAuth verification** — required for >100 Google users; plan brand + privacy policy
3. **Meridian Pro** — multi-account first paid unlock (~$49–79/yr); week view later
4. **License check** — local key or simple store (Gumroad / Lemon Squeezy); no sync SaaS
5. **Audience** — GNOME / Linux productivity, Google Workspace freelancers, “Calendar+Tasks without GOA”

Do not expand the free MVP much further until Pro packaging and a public listing exist.

## Privacy

Refresh tokens live in the Secret Service. A Desktop client secret in the binary is public by Google’s model; verify the OAuth brand before wide Flathub distribution.

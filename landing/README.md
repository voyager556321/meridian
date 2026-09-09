# Meridian landing

Static early-access page (`index.html`).

## Preview locally

```bash
cd /home/admin/projects/meridian/landing
python3 -m http.server 8765
# open http://127.0.0.1:8765/
```

Icon path: `meridian.svg` next to `index.html`.

## Capture emails for real

1. Create a free [Formspree](https://formspree.io) or [Getform](https://getform.io) form.
2. On `#waitlist-form` set `data-endpoint="https://formspree.io/f/YOUR_ID"`.
3. Replace `hello@meridian.local` with your real address.

Until then, submit opens a mailto — fine for the first 10–20 people.

## Deploy (Vercel)

Repo is [voyager556321/meridian](https://github.com/voyager556321/meridian).

1. Import the GitHub repo in Vercel.
2. Set **Root Directory** to `landing`.
3. Framework: Other / no build command.
4. Deploy → you get `*.vercel.app`. Add a custom domain in Project → Settings → Domains.

CLI (from repo root):

```bash
npx vercel --cwd landing --prod
```

## Capture emails for real

Goal: **emails + “I’d use/pay” replies**, not likes.

| Channel | Why it fits | What to post |
|---|---|---|
| **r/gnome**, **r/linux**, **r/linuxapps** | Exact audience | Short demo GIF + link + ask: “Calendar+Tasks native — would you use this?” |
| **Show HN** (news.ycombinator.com) | Builders + power users | “Show HN: Meridian – Google Calendar+Tasks in a Libadwaita window” |
| **Lobsters** (`linux`, `show`) | Smaller, high-signal | Same; ask what would make them pay |
| **GNOME Discourse** / Matrix | Upstream-adjacent | Honest WIP, not spam; invite feedback |
| **Mastodon** `#Linux` `#GNOME` | Organic Linux crowd | 1 screenshot + waitlist |
| **OMG! Ubuntu / It’s FOSS tips** | Reach after packaging | When you have AppImage/Flatpak |
| **DOU / Telegram Linux UA** | Your language, real peers | “Чи потрібно комусь окрім мене?” + waitlist |
| **Product Hunt** | Later | After Flathub + polished demo — not day one |

### Signals that mean “not only for me”

- Waitlist signups from strangers (target: **20+** before investing in Pro billing)
- Comments that name a pain (“I keep Tasks in a tab forever”)
- People asking for **multi-account / work+personal** → Pro thesis confirmed
- Someone offers to beta-test on their distro

Ignore: friend likes, empty GitHub stars, “cool project” with zero email.

### Post template (EN)

> Built a small GNOME app that puts **Google Calendar + Tasks** in one Libadwaita Today view (local cache, keyring tokens, no web UI).
> Looking for people who actually live in Google on Linux — would you try this / pay for multi-account later?
> Waitlist: \<link\>

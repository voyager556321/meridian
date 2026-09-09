# Distribution — Arch + Ubuntu

Meridian is a Python/GTK app. You do **not** need Reddit. Ship packages and share the links.

## Quick path (both machines)

```bash
./scripts/install-deps.sh   # pacman or apt
./scripts/install.sh        # ~/.local install
meridian
```

## Arch — local package (then AUR later)

On the Arch box:

```bash
./scripts/makepkg-local.sh
sudo pacman -U dist/meridian-*.pkg.tar.zst
```

When the repo is public and tagged `v0.1.0`:

1. Edit `packaging/aur/PKGBUILD` → set real `url` and a real `sha256sums`.
2. Publish to the AUR as `meridian` (or `meridian-git` for VCS).
3. Users: `yay -S meridian`

## Ubuntu — `.deb`

On the Ubuntu box (needs `dpkg-deb`, usually preinstalled):

```bash
chmod +x scripts/*.sh
./scripts/build-deb.sh
sudo apt install ./dist/meridian_0.1.0-1_all.deb
```

Put the `.deb` on a GitHub Release. Ubuntu users download + `apt install ./meridian_*.deb`.

## What to put on the landing / posts

| Artifact | Who |
|----------|-----|
| `install-deps.sh` + `install.sh` | Testers cloning the repo |
| `meridian_*.deb` | Ubuntu |
| `meridian-*.pkg.tar.zst` or AUR | Arch |
| Flathub (later) | Everyone else |

## Order that works without karma

1. Public GitHub + Release with `.deb` + optional Arch pkg  
2. Mastodon / DOU / Telegram / Show HN with those links  
3. AUR package once the repo is public  
4. Flathub when OAuth brand + metainfo are ready  

AppImage is optional later; `.deb` + AUR already cover your two distros.

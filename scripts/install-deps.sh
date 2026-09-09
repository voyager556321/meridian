#!/usr/bin/env bash
# Install system dependencies for Meridian on Arch or Ubuntu/Debian.
set -euo pipefail

if [[ -f /etc/arch-release ]] || command -v pacman >/dev/null 2>&1 && [[ -f /etc/pacman.conf ]]; then
  echo "Arch-like: installing deps with pacman…"
  sudo pacman -S --needed --noconfirm \
    python python-gobject python-requests \
    gtk4 libadwaita libsecret gobject-introspection
elif command -v apt-get >/dev/null 2>&1; then
  echo "Debian/Ubuntu: installing deps with apt…"
  sudo apt-get update
  sudo apt-get install -y \
    python3 python3-gi python3-requests \
    gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-secret-1 \
    libgtk-4-1 libadwaita-1-0 libsecret-1-0
else
  echo "Unknown distro. Need Python3 + PyGObject + GTK4 + Libadwaita + libsecret + requests." >&2
  exit 1
fi

echo "Deps OK. Next: ./scripts/install.sh   OR build a package (see packaging/README.md)"

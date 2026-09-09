#!/usr/bin/env bash
# Build a simple .deb for Ubuntu/Debian (arch: all, Python + GObject deps).
# Run on Ubuntu: ./scripts/build-deb.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKGVER="${PKGVER:-0.1.0}"
PKGREL="${PKGREL:-1}"
ARCH="all"
NAME="meridian"
DEB_ROOT="$ROOT/dist/deb/$NAME"
OUT="$ROOT/dist/${NAME}_${PKGVER}-${PKGREL}_${ARCH}.deb"

rm -rf "$ROOT/dist/deb"
mkdir -p \
  "$DEB_ROOT/DEBIAN" \
  "$DEB_ROOT/usr/lib/$NAME" \
  "$DEB_ROOT/usr/bin" \
  "$DEB_ROOT/usr/share/applications" \
  "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps" \
  "$DEB_ROOT/usr/share/doc/$NAME"

PY_FILES=(
  main.py ui.py auth.py config.py db.py secrets_store.py
  oauth_defaults.py google_calendar.py google_tasks.py sync_engine.py
)
for f in "${PY_FILES[@]}"; do
  install -m 0644 "$ROOT/$f" "$DEB_ROOT/usr/lib/$NAME/$f"
done

install -m 0755 /dev/stdin "$DEB_ROOT/usr/bin/meridian" <<'EOF'
#!/bin/bash
exec /usr/bin/python3 /usr/lib/meridian/main.py "$@"
EOF

install -m 0644 "$ROOT/meridian.desktop" \
  "$DEB_ROOT/usr/share/applications/meridian.desktop"
install -m 0644 "$ROOT/data/icons/hicolor/scalable/apps/meridian.svg" \
  "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps/meridian.svg"
install -m 0644 "$ROOT/README.md" "$DEB_ROOT/usr/share/doc/$NAME/README.md"

SIZE_KB="$(du -sk "$DEB_ROOT" | cut -f1)"

cat > "$DEB_ROOT/DEBIAN/control" <<EOF
Package: $NAME
Version: $PKGVER-$PKGREL
Section: gnome
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE_KB
Depends: python3 (>= 3.10), python3-gi, python3-requests, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-secret-1, libgtk-4-1, libadwaita-1-0, libsecret-1-0
Maintainer: Meridian contributors <hello@meridian.local>
Homepage: https://github.com/YOUR_USER/meridian
Description: Google Calendar and Tasks for GNOME
 Meridian is a local-first Libadwaita Today hub for Google Calendar and Tasks.
EOF

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$DEB_ROOT" "$OUT"
echo "Built: $OUT"
echo "Install with: sudo apt install ./dist/$(basename "$OUT")"

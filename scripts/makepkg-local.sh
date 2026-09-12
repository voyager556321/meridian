#!/usr/bin/env bash
# Build an Arch package from the current tree (no public tag required).
# Run on Arch: ./scripts/makepkg-local.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/dist/aur-build"
PKGVER="${PKGVER:-0.1.0}"

rm -rf "$BUILD"
mkdir -p "$BUILD/meridian-$PKGVER" "$ROOT/dist"

# Stage a clean source tree (no rsync required)
tar -C "$ROOT" \
  --exclude=".venv" --exclude=".git" --exclude="dist" \
  --exclude="__pycache__" --exclude="*.pyc" --exclude=".gitignore" \
  --exclude="oauth_defaults.local.py" \
  -cf - . | tar -C "$BUILD/meridian-$PKGVER" -xf -

# Inject maintainer OAuth into the package tree only (not git).
if [[ -f "$ROOT/oauth_defaults.local.py" ]]; then
  python3 - "$ROOT/oauth_defaults.local.py" "$BUILD/meridian-$PKGVER/oauth_defaults.py" <<'PY'
import importlib.util, sys
from pathlib import Path
local, dest = Path(sys.argv[1]), Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("odl", local)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
cid = getattr(mod, "BUNDLED_CLIENT_ID", "") or ""
sec = getattr(mod, "BUNDLED_CLIENT_SECRET", "") or ""
dest.write_text(
    "\"\"\"Bundled OAuth for packaged Meridian builds (generated; not from public git).\"\"\"\n"
    "from __future__ import annotations\n\n"
    f"BUNDLED_CLIENT_ID = {cid!r}\n"
    f"BUNDLED_CLIENT_SECRET = {sec!r}\n\n"
    "def bundled_client_id() -> str:\n"
    "    return (BUNDLED_CLIENT_ID or \"\").strip()\n\n"
    "def bundled_client_secret() -> str:\n"
    "    return (BUNDLED_CLIENT_SECRET or \"\").strip()\n\n"
    "def has_bundled_client() -> bool:\n"
    "    cid = bundled_client_id()\n"
    "    return bool(cid) and \"apps.googleusercontent.com\" in cid and \"@\" not in cid\n"
)
print("injected OAuth into package tree from oauth_defaults.local.py")
PY
fi

cd "$BUILD"
tar -czf "meridian-$PKGVER.tar.gz" "meridian-$PKGVER"

cp "$ROOT/packaging/aur/PKGBUILD" "$BUILD/PKGBUILD"
sed -i \
  -e "s|^pkgver=.*|pkgver=$PKGVER|" \
  -e "s|^source=.*|source=(\"meridian-\$pkgver.tar.gz\")|" \
  -e "s|^sha256sums=.*|sha256sums=('SKIP')|" \
  -e "/^url=/c\url=\"local\"" \
  "$BUILD/PKGBUILD"

makepkg -f
mv -f "$BUILD"/meridian-*.pkg.tar.* "$ROOT/dist/"
echo "Built:"
ls -1 "$ROOT/dist"/meridian-*.pkg.tar.*
echo
echo "Install with: sudo pacman -U dist/meridian-*.pkg.tar.*"

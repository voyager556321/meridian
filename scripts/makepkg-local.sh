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
  --exclude='.venv' --exclude='.git' --exclude='dist' \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='.gitignore' \
  -cf - . | tar -C "$BUILD/meridian-$PKGVER" -xf -

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

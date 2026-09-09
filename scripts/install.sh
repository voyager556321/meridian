#!/usr/bin/env bash
# Install Meridian into ~/.local for the current user (no root required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${PREFIX}/meridian"
ICON_DIR="${PREFIX}/icons/hicolor/scalable/apps"
DESKTOP_DIR="${PREFIX}/applications"
VENV="${APP_DIR}/.venv"

mkdir -p "${APP_DIR}" "${BIN_DIR}" "${ICON_DIR}" "${DESKTOP_DIR}"
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/meridian"

PY_FILES=(
  main.py ui.py auth.py config.py db.py secrets_store.py
  oauth_defaults.py google_calendar.py google_tasks.py sync_engine.py
)
for f in "${PY_FILES[@]}"; do
  install -m 0644 "${ROOT}/${f}" "${APP_DIR}/${f}"
done
install -m 0644 "${ROOT}/requirements.txt" "${APP_DIR}/requirements.txt"
install -m 0644 "${ROOT}/data/icons/hicolor/scalable/apps/meridian.svg" \
  "${ICON_DIR}/meridian.svg"

if [[ ! -x "${VENV}/bin/python" ]]; then
  # Prefer a venv only when system requests is missing
  if /usr/bin/python3 -c "import requests" 2>/dev/null; then
    :
  elif command -v virtualenv >/dev/null 2>&1; then
    virtualenv --python=/usr/bin/python3 --system-site-packages "${VENV}"
  else
    /usr/bin/python3 -m venv --system-site-packages "${VENV}"
  fi
fi
if [[ -x "${VENV}/bin/pip" ]]; then
  "${VENV}/bin/pip" install --upgrade pip
  "${VENV}/bin/pip" install -r "${APP_DIR}/requirements.txt"
fi

if [[ -x "${VENV}/bin/python" ]]; then
  PY="${VENV}/bin/python"
else
  PY="/usr/bin/python3"
fi

cat > "${BIN_DIR}/meridian" <<EOF
#!/usr/bin/env bash
exec "${PY}" "${APP_DIR}/main.py" "\$@"
EOF
chmod 0755 "${BIN_DIR}/meridian"

sed "s|^Exec=.*|Exec=${BIN_DIR}/meridian|" "${ROOT}/meridian.desktop" \
  > "${DESKTOP_DIR}/meridian.desktop"

if [[ ! -f "${XDG_CONFIG_HOME:-$HOME/.config}/meridian/config.json" ]]; then
  install -m 0600 "${ROOT}/config.json.example" \
    "${XDG_CONFIG_HOME:-$HOME/.config}/meridian/config.json"
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f "${PREFIX}/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
fi

echo "Installed Meridian MVP"
echo "  binary : ${BIN_DIR}/meridian"
echo "  desktop: ${DESKTOP_DIR}/meridian.desktop"
echo
echo "Ensure ${BIN_DIR} is on your PATH, then run: meridian"

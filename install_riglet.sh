#!/bin/bash
set -Eeuo pipefail

trap 'echo "Installer failed on line $LINENO"; exit 1' ERR

# --- CONFIG ---
SRC_DIR="$(pwd)"                       # run from repo root
DEST_BIN="/usr/local/bin"
DEST_SYS="/etc/systemd/system"

PY_FILES=( "midi_autopatch_generic.py" "clock2po_generic.py" )
OPT_PY="sensehat_monitor.py"
SVC_FILES=( "midi-autopatch.service" "clock2po.service" )
OPT_SVC="sensehat-monitor.service"

# --- Helpers ---
die() { echo "Error: $*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || die "python3 not found (unexpected on Pi OS)"

need_file() {
  local f="$1"
  [[ -f "$SRC_DIR/$f" ]] || die "Required file not found: $f (run from repo root?)"
}

maybe_copy() {
  local src="$1" dest="$2"
  if [[ -f "$SRC_DIR/$src" ]]; then
    sudo cp "$SRC_DIR/$src" "$dest/"
  fi
}

echo "=== Riglet Installer ==="

# Sanity checks
for f in "${PY_FILES[@]}"; do need_file "$f"; done
for f in "${SVC_FILES[@]}"; do need_file "$f"; done

# Ensure destinations exist
sudo install -d -m 0755 "$DEST_BIN" "$DEST_SYS"

# 1) Dependencies
echo "[1/5] Installing dependencies..."
sudo apt update
sudo apt install -y \
  python3-pip alsa-utils \
  python3-mido python3-rtmidi python3-alsaaudio

# If you plan to use Sense HAT and the optional files are present, install these too:
if [[ -f "$SRC_DIR/$OPT_PY" || -f "$SRC_DIR/$OPT_SVC" ]]; then
  echo "[1b] Optional: installing Sense HAT packages..."
  sudo apt install -y sense-hat python3-sense-hat || true
fi

# 2) Copy Python scripts
echo "[2/5] Copying Python scripts to $DEST_BIN ..."
for f in "${PY_FILES[@]}"; do
  sudo cp "$SRC_DIR/$f" "$DEST_BIN/"
done
maybe_copy "$OPT_PY" "$DEST_BIN"

# 3) Permissions
echo "[3/5] Setting executable permissions..."
for f in "${PY_FILES[@]}"; do
  sudo chmod +x "$DEST_BIN/$f"
done
if [[ -f "$DEST_BIN/$OPT_PY" ]]; then
  sudo chmod +x "$DEST_BIN/$OPT_PY"
fi

# 4) Copy systemd service files
echo "[4/5] Installing systemd services to $DEST_SYS ..."
for f in "${SVC_FILES[@]}"; do
  sudo cp "$SRC_DIR/$f" "$DEST_SYS/"
done
maybe_copy "$OPT_SVC" "$DEST_SYS"

# 5) Reload + enable services
echo "[5/5] Enabling services..."
sudo systemctl daemon-reload
sudo systemctl enable --now midi-autopatch.service
sudo systemctl enable --now clock2po.service
if [[ -f "$DEST_SYS/$OPT_SVC" ]]; then
  sudo systemctl enable --now sensehat-monitor.service || true
fi

echo "=== Riglet install complete! ==="
echo "Check status:"
echo "  systemctl status midi-autopatch.service clock2po.service"

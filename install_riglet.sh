#!/bin/bash
set -e

# --- CONFIG ---
SRC_DIR="$(pwd)"   # assumes you're running this in the repo root
DEST_BIN="/usr/local/bin"
DEST_SYS="/etc/systemd/system"

echo "=== Riglet Installer ==="

# 1. Install dependencies
echo "[1/5] Installing dependencies..."
sudo apt update
sudo apt install -y python3-pip alsa-utils python3-mido python3-rtmidi python3-alsaaudio

# 2. Copy Python scripts
echo "[2/5] Copying Python scripts..."
sudo cp "$SRC_DIR/midi_autopatch_generic.py" "$DEST_BIN/"
sudo cp "$SRC_DIR/clock2po_generic.py" "$DEST_BIN/"
if [ -f "$SRC_DIR/sensehat_monitor.py" ]; then
    sudo cp "$SRC_DIR/sensehat_monitor.py" "$DEST_BIN/"
fi

# 3. Set executable permissions
echo "[3/5] Setting permissions..."
sudo chmod +x "$DEST_BIN/midi_autopatch_generic.py"
sudo chmod +x "$DEST_BIN/clock2po_generic.py"
if [ -f "$DEST_BIN/sensehat_monitor.py" ]; then
    sudo chmod +x "$DEST_BIN/sensehat_monitor.py"
fi

# 4. Copy systemd service files
echo "[4/5] Installing systemd services..."
sudo cp "$SRC_DIR/midi-autopatch.service" "$DEST_SYS/"
sudo cp "$SRC_DIR/clock2po.service" "$DEST_SYS/"
if [ -f "$SRC_DIR/sensehat-monitor.service" ]; then
    sudo cp "$SRC_DIR/sensehat-monitor.service" "$DEST_SYS/"
fi

# 5. Reload + enable services
echo "[5/5] Enabling services..."
sudo systemctl daemon-reload
sudo systemctl enable --now midi-autopatch.service
sudo systemctl enable --now clock2po.service
if [ -f "$DEST_SYS/sensehat-monitor.service" ]; then
    sudo systemctl enable --now sensehat-monitor.service
fi

echo "=== Riglet install complete! ==="
echo "Check services with: systemctl status midi-autopatch clock2po"

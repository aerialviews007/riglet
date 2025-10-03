#!/usr/bin/env bash
# Riglet installer (Pi OS Bookworm + Pirate Audio)
# - Installs deps
# - Installs Python scripts
# - Creates/updates systemd services
# - Enables services

set -euo pipefail

# ----- config -----
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="/usr/local/bin"
MIDIAUTO_PY="midi_autopatch_generic.py"
CLOCK2PO_PY="clock2po_generic.py"

MIDIAUTO_SERVICE="/etc/systemd/system/midi-autopatch.service"
CLOCK2PO_SERVICE="/etc/systemd/system/clock2po.service"

NEEDED_APT_PKGS=( git alsa-utils python3-pip python3-rtmidi python3-mido python3-alsaaudio )
# ------------------

need_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Please run as root:  sudo $0" >&2
    exit 1
  fi
}

apt_install() {
  echo ">>> Installing apt packages: ${NEEDED_APT_PKGS[*]}"
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y "${NEEDED_APT_PKGS[@]}"
}

check_sources() {
  for f in "$MIDIAUTO_PY" "$CLOCK2PO_PY"; do
    if [[ ! -f "$SRC_DIR/$f" ]]; then
      echo "ERROR: Missing $f in $SRC_DIR" >&2
      exit 1
    fi
  done
}

install_bins() {
  echo ">>> Installing Python scripts to $BIN_DIR"
  install -m 0755 "$SRC_DIR/$MIDIAUTO_PY" "$BIN_DIR/$MIDIAUTO_PY"
  install -m 0755 "$SRC_DIR/$CLOCK2PO_PY" "$BIN_DIR/$CLOCK2PO_PY"
}

write_services() {
  echo ">>> Writing systemd unit: $MIDIAUTO_SERVICE"
  cat > "$MIDIAUTO_SERVICE" <<'EOF'
[Unit]
Description=Riglet MIDI autopatch (ALSA)
After=multi-user.target sound.target
Wants=sound.target

[Service]
Type=simple
# Wait up to 10s for ALSA/aconnect to be usable
ExecStartPre=/bin/sh -c 'for i in $(seq 1 10); do aconnect -l >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1'
ExecStart=/usr/bin/python3 /usr/local/bin/midi_autopatch_generic.py
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
EOF

  echo ">>> Writing systemd unit: $CLOCK2PO_SERVICE"
  cat > "$CLOCK2PO_SERVICE" <<'EOF'
[Unit]
Description=MIDI clock -> Pocket Operator sync (Pirate Audio DAC)
After=multi-user.target sound.target
Wants=sound.target

[Service]
Type=simple
# Wait (up to 30s) for an ALSA card so the script doesn't crash on boot
ExecStartPre=/bin/sh -c 'for i in $(seq 1 30); do aplay -l >/dev/null 2>&1 && exit 0; sleep 1; done; echo "No ALSA card found" >&2; exit 1'
ExecStart=/usr/bin/python3 /usr/local/bin/clock2po_generic.py
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
EOF
}

ensure_asound_default() {
  # Only create /etc/asound.conf if it doesn't exist; we won't clobber user config.
  if [[ ! -f /etc/asound.conf ]]; then
    echo ">>> Creating /etc/asound.conf (defaults to card 0)."
    # If Pirate Audio is card 1 on your system, change 'card 0' to 'card 1' after install.
    cat > /etc/asound.conf <<'EOF'
pcm.!default { type hw card 0 }
ctl.!default { type hw card 0 }
EOF
  else
    echo ">>> /etc/asound.conf already exists; leaving it untouched."
  fi
}

enable_services() {
  echo ">>> Enabling services"
  systemctl daemon-reload
  systemctl enable --now midi-autopatch.service
  systemctl enable --now clock2po.service
}

post_notes() {
  echo
  echo "============================================"
  echo " Riglet install complete."
  echo "--------------------------------------------"
  echo "• Verify your Pirate Audio DAC overlay:"
  echo "    sudo dtoverlay -l   # should list hifiberry-dac"
  echo "    aplay -l            # should show sndrpihifiberry"
  echo
  echo "• If speaker-test fails with 'device busy', stop Riglet temporarily:"
  echo "    sudo systemctl stop clock2po.service"
  echo "    speaker-test -D default -c 2 -t wav"
  echo
  echo "• If your DAC is card 1, edit /etc/asound.conf:"
  echo "    sudo nano /etc/asound.conf   # change 'card 0' -> 'card 1'"
  echo "    sudo systemctl restart clock2po.service"
  echo
  echo "• Logs:"
  echo "    journalctl -u midi-autopatch.service -f"
  echo "    journalctl -u clock2po.service -f"
  echo "============================================"
}

main() {
  need_root
  check_sources
  apt_install
  install_bins
  write_services
  ensure_asound_default
  enable_services
  post_notes
}

main "$@"

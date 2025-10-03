#!/usr/bin/env bash
# Riglet uninstaller
# Removes:
#  - clock2po + midi-autopatch services
#  - clock2po_generic.py + midi_autopatch_generic.py
#  - /etc/asound.conf (optional, prompt)

set -euo pipefail

BIN_DIR="/usr/local/bin"
MIDIAUTO_PY="midi_autopatch_generic.py"
CLOCK2PO_PY="clock2po_generic.py"

MIDIAUTO_SERVICE="/etc/systemd/system/midi-autopatch.service"
CLOCK2PO_SERVICE="/etc/systemd/system/clock2po.service"

need_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Please run as root:  sudo $0" >&2
    exit 1
  fi
}

remove_services() {
  echo ">>> Stopping and disabling Riglet services..."
  for svc in "$MIDIAUTO_SERVICE" "$CLOCK2PO_SERVICE"; do
    if [[ -f "$svc" ]]; then
      systemctl disable --now "$(basename "$svc")" || true
      rm -f "$svc"
      echo "Removed service: $svc"
    fi
  done
  systemctl daemon-reload
}

remove_bins() {
  echo ">>> Removing Python scripts..."
  for f in "$MIDIAUTO_PY" "$CLOCK2PO_PY"; do
    if [[ -f "$BIN_DIR/$f" ]]; then
      rm -f "$BIN_DIR/$f"
      echo "Removed: $BIN_DIR/$f"
    fi
  done
}

remove_asound() {
  if [[ -f /etc/asound.conf ]]; then
    read -rp "Remove /etc/asound.conf? [y/N] " yn
    case "$yn" in
      [Yy]*)
        rm -f /etc/asound.conf
        echo "Removed /etc/asound.conf"
        ;;
      *) echo "Kept /etc/asound.conf" ;;
    esac
  fi
}

post_notes() {
  echo
  echo "============================================"
  echo " Riglet uninstall complete."
  echo "--------------------------------------------"
  echo "• Services removed: midi-autopatch, clock2po"
  echo "• Python scripts removed from $BIN_DIR"
  echo "• Check: sudo systemctl list-unit-files | grep -E 'midi|clock2po'"
  echo "• Logs may still exist: journalctl -u midi-autopatch -u clock2po"
  echo "============================================"
}

main() {
  need_root
  remove_services
  remove_bins
  remove_asound
  post_notes
}

main "$@"

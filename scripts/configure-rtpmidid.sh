#!/usr/bin/env bash
# Installa configurazione rtpmidid per annuncio RTP-MIDI su rete
set -euo pipefail

SRC="${1:-/opt/tabloza/config/rtpmidid/default.ini}"
DEST_DIR="/etc/rtpmidid"
DEST="${DEST_DIR}/default.ini"

install -d "${DEST_DIR}"
install -m 644 "${SRC}" "${DEST}"

# Socket controllo
install -d /var/run/rtpmidid

echo "rtpmidid config installata: ${DEST}"

#!/usr/bin/env bash
# Avahi: annuncia HTTP su tabloza-me.local
# RTP-MIDI è annunciato solo da rtpmidid ([rtpmidi_announce]) — niente duplicati Avahi.
set -euo pipefail

INSTALL_DIR="${1:-/opt/tabloza}"
AVAHI_DIR="/etc/avahi/services"

install -d "${AVAHI_DIR}"
install -m 644 "${INSTALL_DIR}/config/avahi/tabloza-web.service" "${AVAHI_DIR}/tabloza-web.service"
# Rimuovi annuncio RTP-MIDI statico (duplicava rtpmidid → "tabloza-me #1" sul Mac)
rm -f "${AVAHI_DIR}/tabloza-rtpmidi.service"

systemctl restart avahi-daemon

echo "Avahi installato:"
echo "  HTTP:      tabloza-me.local → porta 80"
echo "  RTP-MIDI:  tabloza-me (rtpmidid, _apple-midi._udp porta 5004)"

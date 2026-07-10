#!/usr/bin/env bash
# Avahi: annuncia HTTP e RTP-MIDI (Apple MIDI) su tabloza-me.local
set -euo pipefail

INSTALL_DIR="${1:-/opt/tabloza}"
AVAHI_DIR="/etc/avahi/services"

install -d "${AVAHI_DIR}"
install -m 644 "${INSTALL_DIR}/config/avahi/tabloza-web.service"    "${AVAHI_DIR}/tabloza-web.service"
install -m 644 "${INSTALL_DIR}/config/avahi/tabloza-rtpmidi.service" "${AVAHI_DIR}/tabloza-rtpmidi.service"

systemctl restart avahi-daemon

echo "Avahi installato:"
echo "  HTTP:      tabloza-me.local → porta 80"
echo "  RTP-MIDI:  tabloza-me → _apple-midi._udp porta 5004"

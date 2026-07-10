#!/usr/bin/env bash
# Avahi: annuncia il pannello web HTTP su tabloza-me.local
set -euo pipefail

SRC="${1:-/opt/tabloza/config/avahi/tabloza-web.service}"
DEST="/etc/avahi/services/tabloza-web.service"

install -d /etc/avahi/services
install -m 644 "${SRC}" "${DEST}"
systemctl restart avahi-daemon

echo "Avahi HTTP service installato: tabloza-me.local → porta 80"

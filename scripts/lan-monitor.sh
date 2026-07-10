#!/usr/bin/env bash
# Monitor Ethernet: DHCP normale, poi router condiviso se nessun IP
set -euo pipefail

INSTALL_DIR="${TABLOZA_INSTALL_DIR:-/opt/tabloza}"
CHECK_INTERVAL="${TABLOZA_LAN_CHECK_INTERVAL:-15}"

log() { logger -t tabloza-lan "$*"; }

run_auto() {
    PYTHONPATH="${INSTALL_DIR}/src" python3 -c "
from network_utils import manage_ethernet_auto
manage_ethernet_auto()
" 2>/dev/null || true
}

log "Avvio monitor Ethernet"
run_auto

while true; do
    sleep "$CHECK_INTERVAL"
    run_auto
done

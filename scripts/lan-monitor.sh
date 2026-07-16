#!/usr/bin/env bash
# Monitor Ethernet: DHCP normale, poi router condiviso se nessun IP
set -euo pipefail

INSTALL_DIR="${TABLOZA_INSTALL_DIR:-/opt/tabloza}"
CHECK_INTERVAL="${TABLOZA_LAN_CHECK_INTERVAL:-15}"
FALLBACK_SCRIPT="/usr/local/bin/tabloza-wifi-fallback.sh"
CARRIER_STATE_FILE="/run/tabloza/eth-carrier-on"
TABLOZA_COMMON="${TABLOZA_NETWORK_COMMON:-/usr/local/bin/tabloza-network-common.sh}"
if [[ -f "$TABLOZA_COMMON" ]]; then
    # shellcheck source=/dev/null
    source "$TABLOZA_COMMON"
else
    # shellcheck source=network-common.sh
    source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/network-common.sh"
fi

log() { logger -t tabloza-lan "$*"; }

run_auto() {
    PYTHONPATH="${INSTALL_DIR}/src" python3 -c "
from network_utils import manage_ethernet_auto
manage_ethernet_auto()
" 2>/dev/null || true
}

check_carrier_transition() {
    local was_on=0 is_on=0
    [[ -f "$CARRIER_STATE_FILE" ]] && was_on=1
    if tabloza_eth_carrier_on; then
        is_on=1
    fi

    if [[ "$was_on" -eq 1 && "$is_on" -eq 0 ]]; then
        log "Cavo Ethernet rimosso — avvio fallback WiFi/hotspot"
        nmcli radio wifi on >/dev/null 2>&1 || true
        "$FALLBACK_SCRIPT" || true
    fi

    if [[ "$is_on" -eq 1 ]]; then
        mkdir -p /run/tabloza
        touch "$CARRIER_STATE_FILE"
    else
        rm -f "$CARRIER_STATE_FILE"
    fi
}

log "Avvio monitor Ethernet"
run_auto
check_carrier_transition

while true; do
    sleep "$CHECK_INTERVAL"
    run_auto
    check_carrier_transition
done

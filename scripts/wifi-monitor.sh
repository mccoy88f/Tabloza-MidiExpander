#!/usr/bin/env bash
# Monitor WiFi: fallback al boot + riconnessione/hotspot se la rete cade
set -euo pipefail

HOTSPOT_CONN="tabloza-hotspot"
CHECK_INTERVAL=30
FALLBACK_SCRIPT="/usr/local/bin/tabloza-wifi-fallback.sh"

log() { logger -t tabloza-wifi "$*"; }

is_wlan_connected() {
    local state
    state=$(nmcli -t -f DEVICE,STATE device 2>/dev/null | grep '^wlan0:' | cut -d: -f2 || true)
    [[ "$state" == "connected" ]]
}

is_hotspot_active() {
    local active
    active=$(nmcli -t -f NAME,TYPE connection show --active 2>/dev/null \
        | grep ':802-11-wireless' | head -1 | cut -d: -f1 || true)
    [[ "$active" == "$HOTSPOT_CONN" ]]
}

# Fallback iniziale al boot
log "Avvio monitor WiFi"
"$FALLBACK_SCRIPT" || true

while true; do
    sleep "$CHECK_INTERVAL"

    if [[ -f /run/tabloza/wifi-connecting ]]; then
        continue
    fi

    if is_hotspot_active; then
        continue
    fi

    if ! is_wlan_connected; then
        log "WiFi disconnesso — tentativo riconnessione o hotspot"
        "$FALLBACK_SCRIPT" || true
    fi
done

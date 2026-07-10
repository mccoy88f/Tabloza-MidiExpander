#!/usr/bin/env bash
# WiFi fallback: tenta reti note, poi avvia hotspot dopo 20s
set -euo pipefail

HOTSPOT_CONN="tabloza-hotspot"
TIMEOUT=20
TABLOZA_COMMON="${TABLOZA_NETWORK_COMMON:-/usr/local/bin/tabloza-network-common.sh}"
if [[ -f "$TABLOZA_COMMON" ]]; then
    # shellcheck source=/dev/null
    source "$TABLOZA_COMMON"
else
    # shellcheck source=network-common.sh
    source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/network-common.sh"
fi

log() { logger -t tabloza-wifi "$*"; echo "[tabloza-wifi] $*"; }

# Attendi interfaccia wlan
for i in $(seq 1 30); do
    nmcli -t -f DEVICE,TYPE device status | grep -q "^wlan0:wifi" && break
    sleep 1
done

# Se già connesso a una rete WiFi client, esci
ACTIVE=$(nmcli -t -f NAME,TYPE connection show --active 2>/dev/null | grep ":802-11-wireless" | head -1 | cut -d: -f1)
if [[ -n "$ACTIVE" && "$ACTIVE" != "$HOTSPOT_CONN" ]]; then
    log "Connesso a: ${ACTIVE}"
    exit 0
fi

# Con Ethernet attiva (cavo + IP): non forzare hotspot
if tabloza_eth_has_link; then
    log "Ethernet attiva — configura WiFi dal pannello web (http://tabloza-me.local)"
    exit 0
fi

# Tenta connessione a profili salvati (escluso hotspot)
PROFILES=$(nmcli -t -f NAME,TYPE connection show | grep ":802-11-wireless" | cut -d: -f1 | grep -v "^${HOTSPOT_CONN}$" || true)

if [[ -n "$PROFILES" ]]; then
    log "Tentativo connessione reti note (${TIMEOUT}s timeout)..."
    for profile in $PROFILES; do
        nmcli connection up "$profile" 2>/dev/null &
        UP_PID=$!
        ELAPSED=0
        while kill -0 "$UP_PID" 2>/dev/null && [[ $ELAPSED -lt $TIMEOUT ]]; do
            if nmcli -t -f DEVICE,STATE device show wlan0 2>/dev/null | grep -q "connected"; then
                wait "$UP_PID" 2>/dev/null || true
                log "Connesso a: ${profile}"
                exit 0
            fi
            sleep 1
            ELAPSED=$((ELAPSED + 1))
        done
        kill "$UP_PID" 2>/dev/null || true
        wait "$UP_PID" 2>/dev/null || true
    done
fi

# Fallback hotspot
log "Nessuna rete disponibile. Avvio hotspot ${HOTSPOT_CONN}..."
if ! nmcli connection up "$HOTSPOT_CONN" 2>/dev/null; then
    nmcli device wifi hotspot ifname wlan0 ssid "Tabloza-MidiExpander" password "" 2>/dev/null || true
fi
if nmcli -t -f NAME connection show --active 2>/dev/null | grep -q "^${HOTSPOT_CONN}$"; then
    log "Hotspot attivo."
else
    log "Avvio hotspot fallito — riprova tra poco"
    exit 1
fi

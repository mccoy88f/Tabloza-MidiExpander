#!/usr/bin/env bash
# WiFi fallback: tenta reti note, poi avvia hotspot dopo timeout
set -euo pipefail

HOTSPOT_CONN="tabloza-hotspot"
HOTSPOT_SSID="${TABLOZA_HOTSPOT_SSID:-Tabloza-MidiExpander}"
HOTSPOT_PASSWORD="${TABLOZA_HOTSPOT_PASSWORD:-tabloza1}"
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

ensure_wifi_radio() {
    nmcli radio wifi on >/dev/null 2>&1 || true
    for i in $(seq 1 30); do
        local state
        state=$(nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null \
            | grep "^wlan0:wifi:" | cut -d: -f3 || true)
        if [[ -n "$state" && "$state" != "unavailable" ]]; then
            return 0
        fi
        sleep 1
    done
    log "wlan0 non disponibile dopo attivazione radio"
    return 1
}

start_hotspot() {
    local err=""
    log "Nessuna rete disponibile. Avvio hotspot ${HOTSPOT_CONN}..."
    if ! ensure_wifi_radio; then
        return 1
    fi
    nmcli device disconnect wlan0 >/dev/null 2>&1 || true
    sleep 1

    if nmcli connection up "$HOTSPOT_CONN" 2>/tmp/tabloza-hotspot.err; then
        :
    else
        err=$(tr -d '\n' </tmp/tabloza-hotspot.err 2>/dev/null || true)
        log "connection up fallito: ${err:-?} — tentativo nmcli device wifi hotspot"
        if ! nmcli device wifi hotspot \
            ifname wlan0 \
            ssid "$HOTSPOT_SSID" \
            password "$HOTSPOT_PASSWORD" \
            2>/tmp/tabloza-hotspot.err; then
            err=$(tr -d '\n' </tmp/tabloza-hotspot.err 2>/dev/null || true)
            log "Avvio hotspot fallito: ${err:-sconosciuto}"
            return 1
        fi
        # Allinea nome profilo se NM ha creato Hotspot-xxx
        local active
        active=$(nmcli -t -f NAME,TYPE connection show --active 2>/dev/null \
            | grep ':802-11-wireless' | head -1 | cut -d: -f1 || true)
        if [[ -n "$active" && "$active" != "$HOTSPOT_CONN" ]]; then
            nmcli connection modify "$active" connection.id "$HOTSPOT_CONN" 2>/dev/null || true
        fi
    fi

    if nmcli -t -f NAME connection show --active 2>/dev/null | grep -q "^${HOTSPOT_CONN}$" \
        || nmcli -t -f DEVICE,STATE device status 2>/dev/null | grep -q '^wlan0:connected'; then
        log "Hotspot attivo (SSID ${HOTSPOT_SSID}, password ${HOTSPOT_PASSWORD})."
        return 0
    fi
    log "Avvio hotspot fallito — riprova tra poco"
    return 1
}

# Riaccende sempre la radio (può essere stata spenta dal pannello con cavo LAN)
ensure_wifi_radio || true

# Se già connesso a una rete WiFi client, esci
ACTIVE=$(nmcli -t -f NAME,TYPE connection show --active 2>/dev/null | grep ":802-11-wireless" | head -1 | cut -d: -f1 || true)
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
PROFILES=$(nmcli -t -f NAME,TYPE connection show 2>/dev/null | grep ":802-11-wireless" | cut -d: -f1 | grep -v "^${HOTSPOT_CONN}$" || true)

if [[ -n "$PROFILES" ]]; then
    log "Tentativo connessione reti note (${TIMEOUT}s timeout)..."
    for profile in $PROFILES; do
        nmcli connection up "$profile" 2>/dev/null &
        UP_PID=$!
        ELAPSED=0
        while kill -0 "$UP_PID" 2>/dev/null && [[ $ELAPSED -lt $TIMEOUT ]]; do
            if nmcli -t -f DEVICE,STATE device 2>/dev/null | grep -q '^wlan0:connected'; then
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

start_hotspot

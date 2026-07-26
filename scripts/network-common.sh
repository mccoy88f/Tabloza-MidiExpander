#!/usr/bin/env bash
# Funzioni condivise per monitor WiFi/Ethernet Tabloza
tabloza_eth_device() {
    nmcli -t -f DEVICE,TYPE device status 2>/dev/null | grep ':ethernet' | head -1 | cut -d: -f1
}

tabloza_eth_carrier_on() {
    local dev carrier
    dev=$(tabloza_eth_device)
    [[ -z "$dev" ]] && return 1
    carrier=$(nmcli -g WIRED-PROPERTIES.CARRIER device show "$dev" 2>/dev/null | tr '[:upper:]' '[:lower:]')
    [[ "$carrier" == "on" || "$carrier" == "yes" || "$carrier" == "true" || "$carrier" == "1" ]]
}

# Ethernet utilizzabile: cavo inserito (carrier) e indirizzo IPv4 valido
tabloza_eth_has_link() {
    local dev ip
    tabloza_eth_carrier_on || return 1
    dev=$(tabloza_eth_device)
    ip=$(nmcli -g IP4.ADDRESS device show "$dev" 2>/dev/null | head -1 | cut -d/ -f1)
    [[ -n "$ip" && "$ip" != "--" && ! "$ip" =~ ^169\.254\. ]]
}

# Adotta il profilo WiFi client attivo come profilo Tabloza: se non è già
# "tabloza-wifi-*" lo rinomina (senza disconnettere) in tabloza-wifi-<ssid>,
# forza powersave=2 e rimuove eventuali altri profili residui per la stessa
# SSID (es. netplan-* creati dall'immagine base prima di installare Tabloza).
# Così resta sempre un solo profilo gestito, con il fix del power-save.
tabloza_claim_wifi_profile() {
    local hotspot_conn="${HOTSPOT_CONN:-tabloza-hotspot}"
    local active
    active=$(nmcli -t -f NAME,TYPE connection show --active 2>/dev/null \
        | grep ':802-11-wireless' | head -1 | cut -d: -f1) || true
    if [[ -z "${active:-}" ]]; then
        return 0
    fi
    if [[ "$active" == "$hotspot_conn" ]]; then
        return 0
    fi
    if [[ "$active" == tabloza-wifi-* ]]; then
        return 0
    fi

    local ssid
    ssid=$(nmcli -g 802-11-wireless.ssid connection show "$active" 2>/dev/null) || true
    if [[ -z "${ssid:-}" ]]; then
        return 0
    fi

    local safe_ssid new_name
    safe_ssid=$(printf '%s' "$ssid" | tr -c 'A-Za-z0-9_-' '_' | cut -c1-20)
    new_name="tabloza-wifi-${safe_ssid}"

    if nmcli connection modify "$active" \
        connection.id "$new_name" \
        802-11-wireless.powersave 2 \
        connection.autoconnect yes \
        connection.autoconnect-priority 100 2>/dev/null; then
        logger -t tabloza-wifi "Profilo WiFi «${active}» adottato come «${new_name}» (powersave disabilitato)"
    else
        return 0
    fi

    local name conn_type other_ssid
    while IFS=: read -r name conn_type; do
        if [[ "$conn_type" != "802-11-wireless" ]]; then
            continue
        fi
        if [[ "$name" == "$hotspot_conn" || "$name" == "$new_name" ]]; then
            continue
        fi
        other_ssid=$(nmcli -g 802-11-wireless.ssid connection show "$name" 2>/dev/null) || true
        if [[ "${other_ssid:-}" == "$ssid" ]]; then
            nmcli connection delete "$name" >/dev/null 2>&1 || true
            logger -t tabloza-wifi "Rimosso profilo WiFi residuo: ${name}"
        fi
    done < <(nmcli -t -f NAME,TYPE connection show 2>/dev/null || true)
    return 0
}

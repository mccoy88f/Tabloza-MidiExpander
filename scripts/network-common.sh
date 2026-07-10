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

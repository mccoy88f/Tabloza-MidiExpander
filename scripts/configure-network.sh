#!/usr/bin/env bash
# Configura NetworkManager: profili WiFi client + hotspot fallback
set -euo pipefail

HOTSPOT_SSID="${1:-Tabloza-MidiExpander}"
HOTSPOT_IP="${2:-192.168.4.1}"

# Assicura NetworkManager attivo
systemctl enable NetworkManager
systemctl start NetworkManager

CONN_NAME="tabloza-hotspot"
NM_CONN="/etc/NetworkManager/system-connections/${CONN_NAME}.nmconnection"

if [[ ! -f "$NM_CONN" ]]; then
    cat > "$NM_CONN" <<EOF
[connection]
id=${CONN_NAME}
uuid=$(cat /proc/sys/kernel/random/uuid)
type=wifi
autoconnect=false
interface-name=wlan0

[wifi]
mode=ap
ssid=${HOTSPOT_SSID}

[wifi-security]
key-mgmt=none

[ipv4]
method=shared
address1=${HOTSPOT_IP}/24

[ipv6]
method=ignore
EOF
    chmod 600 "$NM_CONN"
fi

# Script WiFi fallback al boot
install -m 755 "$(dirname "$0")/wifi-fallback.sh" /usr/local/bin/tabloza-wifi-fallback.sh

echo "NetworkManager hotspot configurato: ${HOTSPOT_SSID} @ ${HOTSPOT_IP}"

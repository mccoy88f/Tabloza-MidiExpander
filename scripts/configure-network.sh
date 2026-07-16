#!/usr/bin/env bash
# Configura NetworkManager: profili WiFi client + hotspot fallback
set -euo pipefail

HOTSPOT_SSID="${1:-Tabloza-MidiExpander}"
HOTSPOT_IP="${2:-192.168.4.1}"
# WPA2 richiede ≥8 caratteri; rete aperta (key-mgmt=none) spesso non parte o non è visibile
HOTSPOT_PASSWORD="${3:-tabloza1}"

# Assicura NetworkManager attivo
systemctl enable NetworkManager
systemctl start NetworkManager

CONN_NAME="tabloza-hotspot"
NM_CONN="/etc/NetworkManager/system-connections/${CONN_NAME}.nmconnection"
NM_UUID="$(cat /proc/sys/kernel/random/uuid)"
if [[ -f "$NM_CONN" ]]; then
    EXISTING_UUID=$(grep -E '^uuid=' "$NM_CONN" 2>/dev/null | head -1 | cut -d= -f2 || true)
    [[ -n "${EXISTING_UUID:-}" ]] && NM_UUID="$EXISTING_UUID"
fi

# Riscrive sempre il profilo: migra da open AP → WPA2 e allinea SSID/IP
cat > "$NM_CONN" <<EOF
[connection]
id=${CONN_NAME}
uuid=${NM_UUID}
type=wifi
autoconnect=false
interface-name=wlan0

[wifi]
mode=ap
ssid=${HOTSPOT_SSID}

[wifi-security]
key-mgmt=wpa-psk
psk=${HOTSPOT_PASSWORD}

[ipv4]
method=shared
address1=${HOTSPOT_IP}/24

[ipv6]
method=ignore
EOF
chmod 600 "$NM_CONN"
nmcli connection reload 2>/dev/null || true

# Script WiFi fallback + monitor continuo
install -m 755 "$(dirname "$0")/wifi-fallback.sh" /usr/local/bin/tabloza-wifi-fallback.sh
install -m 755 "$(dirname "$0")/wifi-monitor.sh"  /usr/local/bin/tabloza-wifi-monitor.sh
install -m 755 "$(dirname "$0")/lan-monitor.sh"   /usr/local/bin/tabloza-lan-monitor.sh
install -m 644 "$(dirname "$0")/network-common.sh" /usr/local/bin/tabloza-network-common.sh

echo "NetworkManager hotspot configurato: ${HOTSPOT_SSID} @ ${HOTSPOT_IP} (WPA2)"
echo "Password hotspot: ${HOTSPOT_PASSWORD}"
echo "Link LAN diretto: attivabile dal pannello (tabloza-lan-direct @ 192.168.5.1)"

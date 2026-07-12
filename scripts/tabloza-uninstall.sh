#!/usr/bin/env bash
# Tabloza MidiExpander — Disinstallazione
# Uso: sudo tabloza-uninstall
set -euo pipefail

INSTALL_DIR="/opt/tabloza"
DATA_DIR="/var/lib/tabloza"

red() { echo -e "\033[1;31m[Tabloza]\033[0m $*"; }
log() { echo -e "\033[1;32m[Tabloza]\033[0m $*"; }
warn() { echo -e "\033[1;33m[Tabloza]\033[0m $*"; }

[[ $EUID -eq 0 ]] || { red "Esegui come root: sudo tabloza-uninstall"; exit 1; }

# Evita shell con cwd in /opt/tabloza dopo la rimozione (getcwd error al reinstall).
cd / || cd /root || true

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Disinstallazione Tabloza MidiExpander      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
warn "Questo rimuove servizi, configurazioni e /opt/tabloza"
warn "I dati in ${DATA_DIR} (SF2, password) vengono PRESERVATI per default."
echo ""
read -rp "Continuare? [s/N] " CONFIRM
[[ "${CONFIRM,,}" == "s" || "${CONFIRM,,}" == "si" ]] || { log "Annullato."; exit 0; }

read -rp "Eliminare anche i dati (${DATA_DIR})? [s/N] " DELDATA
echo ""

log "Arresto servizi..."
for svc in tabloza-web tabloza-orchestrator tabloza-wifi tabloza-lan tabloza-midi-ws rtpmidid; do
    systemctl stop "$svc" 2>/dev/null || true
    systemctl disable "$svc" 2>/dev/null || true
done

log "Rimozione unit systemd..."
rm -f /etc/systemd/system/tabloza-web.service
rm -f /etc/systemd/system/tabloza-orchestrator.service
rm -f /etc/systemd/system/tabloza-wifi.service
rm -f /etc/systemd/system/tabloza-lan.service
rm -f /etc/systemd/system/tabloza-midi-ws.service
rm -f /etc/systemd/system/rtpmidid.service
systemctl daemon-reload

log "Rimozione script di sistema..."
rm -f /usr/local/bin/tabloza-wifi-fallback.sh
rm -f /usr/local/bin/tabloza-wifi-monitor.sh
rm -f /usr/local/bin/tabloza-lan-monitor.sh
rm -f /usr/local/bin/tabloza-network-common.sh
rm -f /usr/local/bin/tabloza-test
rm -f /usr/local/bin/tabloza-uninstall
rm -f /usr/local/bin/tabloza-update

log "Rimozione configurazioni..."
rm -f /etc/avahi/services/tabloza-web.service
rm -f /etc/avahi/services/tabloza-rtpmidi.service
rm -f /etc/NetworkManager/system-connections/tabloza-hotspot.nmconnection
rm -rf /etc/rtpmidid
systemctl restart avahi-daemon 2>/dev/null || true

log "Rimozione sorgenti..."
rm -rf "${INSTALL_DIR}"

if [[ "${DELDATA,,}" == "s" || "${DELDATA,,}" == "si" ]]; then
    warn "Eliminazione dati in ${DATA_DIR}..."
    rm -rf "${DATA_DIR}"
else
    log "Dati preservati in ${DATA_DIR}"
fi

log ""
log "Disinstallazione completata."
log "Per reinstallare:"
log "  curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash"

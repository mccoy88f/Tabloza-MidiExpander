#!/usr/bin/env bash
# Tabloza MidiExpander — Installer
# https://github.com/mccoy88f/Tabloza-MidiExpander
set -euo pipefail

REPO_URL="https://github.com/mccoy88f/Tabloza-MidiExpander.git"
INSTALL_DIR="/opt/tabloza"
DATA_DIR="/var/lib/tabloza"
SOUNDFONTS_DIR="${DATA_DIR}/soundfonts"
CONFIG_FILE="${DATA_DIR}/config.json"
AUTH_FILE="${DATA_DIR}/auth.json"
DEFAULT_PASSWORD="tabloza"
HOSTNAME="tabloza-midi"
HOTSPOT_SSID="Tabloza-MidiExpander"
HOTSPOT_IP="192.168.4.1"

log()  { echo -e "\033[1;32m[Tabloza]\033[0m $*"; }
warn() { echo -e "\033[1;33m[Tabloza]\033[0m $*"; }
die()  { echo -e "\033[1;31m[Tabloza] ERRORE:\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Esegui come root: curl -fsSL ... | sudo bash"

# --- Verifica piattaforma ---
[[ "$(uname -m)" == "aarch64" ]] || die "Richiesto Raspberry Pi OS 64-bit (aarch64)."

if [[ -f /etc/os-release ]]; then
    # shellcheck source=/dev/null
    source /etc/os-release
    [[ "${ID:-}" == "raspbian" || "${ID:-}" == "debian" ]] || warn "OS non verificato (${ID:-unknown}). Procedo comunque."
else
    die "Impossibile rilevare il sistema operativo."
fi

PI_MODEL=""
if [[ -f /proc/device-tree/model ]]; then
    PI_MODEL="$(tr -d '\0' < /proc/device-tree/model)"
    log "Rilevato: ${PI_MODEL}"
    if echo "$PI_MODEL" | grep -qi "Raspberry Pi 3"; then
        warn "Raspberry Pi 3: supporto limitato. Pi 4/5 consigliati per bassa latenza."
    fi
fi

# --- Dipendenze ---
log "Aggiornamento pacchetti e installazione dipendenze..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    git curl \
    fluidsynth fluid-soundfont-gm \
    rtpmidid \
    avahi-daemon avahi-utils \
    network-manager \
    python3 python3-flask python3-bcrypt python3-venv \
    alsa-utils \
    libasound2-dev

# --- Directory dati persistenti ---
log "Configurazione directory dati in ${DATA_DIR}..."
mkdir -p "${SOUNDFONTS_DIR}"
mkdir -p "${INSTALL_DIR}"

# --- Clone / aggiornamento sorgenti ---
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    log "Aggiornamento sorgenti esistenti..."
    git -C "${INSTALL_DIR}" pull --ff-only origin main
else
    log "Download sorgenti da GitHub..."
    git clone --depth 1 "${REPO_URL}" "${INSTALL_DIR}"
fi

# --- Config persistente ---
if [[ ! -f "${CONFIG_FILE}" ]]; then
    log "Creazione configurazione predefinita..."
    cat > "${CONFIG_FILE}" <<'EOF'
{
  "active_soundfont": "",
  "volume": 100,
  "fluidsynth": {
    "audio_driver": "alsa",
    "audio_device": "plughw:0,0",
    "sample_rate": 44100,
    "period_size": 256,
    "period_count": 4,
    "gain": 0.5
  }
}
EOF
fi

if [[ ! -f "${AUTH_FILE}" ]]; then
    log "Impostazione password predefinita: ${DEFAULT_PASSWORD}"
    HASH=$(python3 -c "import bcrypt; print(bcrypt.hashpw(b'${DEFAULT_PASSWORD}', bcrypt.gensalt()).decode())")
    echo "{\"password_hash\": \"${HASH}\"}" > "${AUTH_FILE}"
    chmod 600 "${AUTH_FILE}"
fi

# --- Hostname e mDNS ---
log "Configurazione hostname ${HOSTNAME}..."
hostnamectl set-hostname "${HOSTNAME}"
if ! grep -q "${HOSTNAME}" /etc/hosts; then
    sed -i "s/127.0.1.1.*/127.0.1.1\t${HOSTNAME}/" /etc/hosts 2>/dev/null || \
        echo -e "127.0.1.1\t${HOSTNAME}" >> /etc/hosts
fi
systemctl enable avahi-daemon
systemctl restart avahi-daemon

# --- UART MIDI 31250 bps ---
log "Configurazione UART MIDI (31250 bps)..."
bash "${INSTALL_DIR}/scripts/configure-midi-uart.sh"

# --- NetworkManager hotspot fallback ---
log "Configurazione WiFi hotspot fallback..."
bash "${INSTALL_DIR}/scripts/configure-network.sh" "${HOTSPOT_SSID}" "${HOTSPOT_IP}"

# --- Permessi audio real-time ---
log "Configurazione priorità audio real-time..."
bash "${INSTALL_DIR}/scripts/configure-audio-rt.sh"

# --- Servizi systemd ---
log "Installazione servizi systemd..."
install -m 644 "${INSTALL_DIR}/systemd/rtpmidid.service"        /etc/systemd/system/rtpmidid.service
install -m 644 "${INSTALL_DIR}/systemd/tabloza-orchestrator.service" /etc/systemd/system/tabloza-orchestrator.service
install -m 644 "${INSTALL_DIR}/systemd/tabloza-web.service"     /etc/systemd/system/tabloza-web.service
install -m 644 "${INSTALL_DIR}/systemd/tabloza-wifi.service"    /etc/systemd/system/tabloza-wifi.service

systemctl daemon-reload
systemctl enable rtpmidid tabloza-orchestrator tabloza-web tabloza-wifi
systemctl restart rtpmidid tabloza-orchestrator tabloza-web tabloza-wifi

# --- Permessi ---
chown -R root:root "${INSTALL_DIR}"
chmod -R 755 "${INSTALL_DIR}"
chown -R root:root "${DATA_DIR}"
chmod 755 "${DATA_DIR}"
chmod 755 "${SOUNDFONTS_DIR}"

log ""
log "============================================"
log "  Installazione completata!"
log "============================================"
log ""
log "  Web UI:    http://${HOSTNAME}.local"
log "  Hotspot:   ${HOTSPOT_SSID} → http://${HOTSPOT_IP}"
log "  Password:  ${DEFAULT_PASSWORD}"
log ""
log "  Riavvia con: sudo reboot"
log "============================================"

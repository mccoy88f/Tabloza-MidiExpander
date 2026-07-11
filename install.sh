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
HOSTNAME="tabloza-me"
HOTSPOT_SSID="Tabloza-MidiExpander"
HOTSPOT_IP="192.168.4.1"
SECRET_FILE="${DATA_DIR}/secret.key"

log()  { echo -e "\033[1;32m[Tabloza]\033[0m $*"; }
warn() { echo -e "\033[1;33m[Tabloza]\033[0m $*"; }
die()  { echo -e "\033[1;31m[Tabloza] ERRORE:\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Esegui come root: curl -fsSL ... | sudo bash"

# La cwd può essere invalida se l'utente ha lanciato l'installer dopo tabloza-uninstall
# da dentro /opt/tabloza (getcwd: cannot access parent directories).
cd / || cd /root || true

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

# --- Bootstrap git (prima di tutto: sblocca /opt/tabloza) ---
log "Bootstrap git..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl

mkdir -p "${INSTALL_DIR}"
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    log "Aggiornamento sorgenti esistenti..."
    git -C "${INSTALL_DIR}" checkout -f main 2>/dev/null || true
    if ! git -C "${INSTALL_DIR}" fetch origin main; then
        warn "Fetch fallito — reinstallazione pulita di ${INSTALL_DIR}"
        rm -rf "${INSTALL_DIR}"
    fi
fi
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    git -C "${INSTALL_DIR}" reset --hard origin/main
    git -C "${INSTALL_DIR}" clean -fd
else
    log "Download sorgenti da GitHub..."
    git clone --depth 1 -b main "${REPO_URL}" "${INSTALL_DIR}"
fi

# --- Dipendenze ---
log "Installazione dipendenze..."
apt-get install -y -qq \
    fluidsynth fluid-soundfont-gm \
    avahi-daemon avahi-utils \
    network-manager \
    python3 python3-flask python3-bcrypt python3-venv python3-pip \
    alsa-utils \
    libasound2-dev

python3 -m pip install --break-system-packages pyalsaaudio 2>/dev/null \
    || python3 -m pip install pyalsaaudio
python3 -m pip install --break-system-packages python-rtmidi 2>/dev/null \
    || python3 -m pip install python-rtmidi

# FluidSynth di sistema (pacchetto fluid-soundfont-gm) confligge con Tabloza.
log "Disabilito FluidSynth di sistema..."
for unit in fluidsynth fluidsynth.service; do
    systemctl stop "$unit" 2>/dev/null || true
    systemctl disable "$unit" 2>/dev/null || true
    systemctl mask "$unit" 2>/dev/null || true
done
pkill -f '/usr/share/sounds/sf3/default-GM' 2>/dev/null || true
pkill -f '/usr/share/sounds/sf2/FluidR3_GM' 2>/dev/null || true
for unit in nginx apache2 lighttpd; do
    systemctl stop "$unit" 2>/dev/null || true
    systemctl disable "$unit" 2>/dev/null || true
    systemctl mask "$unit" 2>/dev/null || true
done

# --- Directory dati persistenti ---
log "Configurazione directory dati in ${DATA_DIR}..."
mkdir -p "${SOUNDFONTS_DIR}"

# --- rtpmidid (da GitHub, non nei repo Pi OS) ---
log "Installazione rtpmidid..."
bash "${INSTALL_DIR}/scripts/install-rtpmidid.sh"
bash "${INSTALL_DIR}/scripts/configure-rtpmidid.sh" "${INSTALL_DIR}/config/rtpmidid/default.ini"

# --- Config persistente ---
if [[ ! -f "${CONFIG_FILE}" ]]; then
    log "Creazione configurazione predefinita..."
    cat > "${CONFIG_FILE}" <<'EOF'
{
  "active_soundfont": "",
  "default_soundfont": "",
  "volume": 100,
  "fluidsynth": {
    "audio_driver": "alsa",
    "audio_device": "plughw:0,0",
    "sample_rate": 44100,
    "period_size": 1024,
    "period_count": 8,
    "gain": 2.0,
    "alsa_card": 0,
    "alsa_mixer_control": "PCM",
    "audio_preset": "stable",
    "polyphony": 256,
    "reverb": true,
    "chorus": true,
    "dynamic_sample_loading": false
  },
  "midi": {
    "jitter_buffer_ms": 25,
    "jitter_buffer_enabled": true,
    "bank_select": "gs"
  }
}
EOF
fi

python3 <<PY
import json
from pathlib import Path
p = Path("${CONFIG_FILE}")
if p.is_file():
    cfg = json.loads(p.read_text())
    midi = cfg.get("midi") if isinstance(cfg.get("midi"), dict) else {}
    changed = False
    if "jitter_buffer_ms" not in midi:
        midi["jitter_buffer_ms"] = 25
        changed = True
    if "jitter_buffer_enabled" not in midi:
        midi["jitter_buffer_enabled"] = True
        changed = True
    if "bank_select" not in midi:
        midi["bank_select"] = "gs"
        changed = True
    if changed:
        cfg["midi"] = midi
        p.write_text(json.dumps(cfg, indent=2) + "\n")
PY

if [[ ! -f "${AUTH_FILE}" ]]; then
    log "Impostazione password predefinita: ${DEFAULT_PASSWORD}"
    HASH=$(python3 -c "import bcrypt; print(bcrypt.hashpw(b'${DEFAULT_PASSWORD}', bcrypt.gensalt()).decode())")
    echo "{\"password_hash\": \"${HASH}\"}" > "${AUTH_FILE}"
    chmod 600 "${AUTH_FILE}"
fi

if [[ ! -f "${SECRET_FILE}" ]]; then
    log "Generazione secret key Flask..."
    python3 -c "import secrets; print(secrets.token_hex(32))" > "${SECRET_FILE}"
    chmod 600 "${SECRET_FILE}"
fi

# --- Hostname e mDNS (tabloza-me.local) ---
log "Configurazione hostname ${HOSTNAME} (mDNS: ${HOSTNAME}.local)..."
hostnamectl set-hostname "${HOSTNAME}"
sed -i "s/127.0.1.1.*/127.0.1.1\t${HOSTNAME}/" /etc/hosts 2>/dev/null || \
    echo -e "127.0.1.1\t${HOSTNAME}" >> /etc/hosts
systemctl enable avahi-daemon
systemctl restart avahi-daemon
bash "${INSTALL_DIR}/scripts/configure-avahi.sh" "${INSTALL_DIR}"

# --- MIDI GPIO UART: funzione pianificata (non attiva) ---
warn "MIDI GPIO fisico: funzione pianificata, non ancora attiva."
warn "Vedi docs/TODO.md — per ora solo RTP-MIDI (rtpmidid)."

# --- NetworkManager hotspot fallback ---
log "Configurazione WiFi hotspot fallback..."
bash "${INSTALL_DIR}/scripts/configure-network.sh" "${HOTSPOT_SSID}" "${HOTSPOT_IP}"

# --- Permessi audio real-time ---
log "Configurazione priorità audio real-time..."
bash "${INSTALL_DIR}/scripts/configure-audio-rt.sh"
install -m 644 "${INSTALL_DIR}/config/modules-load/tabloza.conf" /etc/modules-load.d/tabloza.conf
modprobe snd-seq 2>/dev/null || true

# --- Volume ALSA iniziale (jack cuffie) ---
if command -v amixer >/dev/null; then
    log "Impostazione volume ALSA iniziale..."
    python3 -c "
import sys
sys.path.insert(0, '${INSTALL_DIR}/src')
from tabloza_common import load_config
from audio_utils import apply_output_volume
cfg = load_config()
ok, detail = apply_output_volume(cfg.get('volume', 100), cfg)
print('ALSA:', detail if ok else 'non disponibile — ' + detail)
" || warn "Volume ALSA non impostato (mixer assente o card diversa)"
fi

# --- Comandi di sistema ---
log "Installazione comandi tabloza-test e tabloza-uninstall..."
install -m 755 "${INSTALL_DIR}/scripts/tabloza-test.sh"      /usr/local/bin/tabloza-test
install -m 755 "${INSTALL_DIR}/scripts/tabloza-uninstall.sh"  /usr/local/bin/tabloza-uninstall
install -m 755 "${INSTALL_DIR}/scripts/tabloza-update.sh"    /usr/local/bin/tabloza-update

# --- Servizi systemd ---
log "Installazione servizi systemd..."
install -m 644 "${INSTALL_DIR}/systemd/rtpmidid.service"        /etc/systemd/system/rtpmidid.service
install -m 644 "${INSTALL_DIR}/systemd/tabloza-orchestrator.service" /etc/systemd/system/tabloza-orchestrator.service
install -m 644 "${INSTALL_DIR}/systemd/tabloza-web.service"     /etc/systemd/system/tabloza-web.service
install -m 644 "${INSTALL_DIR}/systemd/tabloza-wifi.service"    /etc/systemd/system/tabloza-wifi.service
install -m 644 "${INSTALL_DIR}/systemd/tabloza-lan.service"     /etc/systemd/system/tabloza-lan.service

systemctl daemon-reload
systemctl enable rtpmidid tabloza-orchestrator tabloza-web tabloza-wifi tabloza-lan
systemctl restart rtpmidid tabloza-orchestrator tabloza-web tabloza-wifi tabloza-lan

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
log "  Web UI:    http://${HOSTNAME}.local  (o http://<IP-del-Pi>)"
log "  mDNS:      ${HOSTNAME}.local"
log "  Hotspot:   ${HOTSPOT_SSID} → http://${HOTSPOT_IP}"
log "  Password:  ${DEFAULT_PASSWORD}"
log ""
log "  Riavvia con: sudo reboot"
log "  Test:       sudo tabloza-test"
log "============================================"

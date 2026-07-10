#!/usr/bin/env bash
# Tabloza MidiExpander — Diagnostica sistema
# Uso: sudo tabloza-test   oppure   bash /opt/tabloza/scripts/tabloza-test.sh
set -uo pipefail

OK=0
WARN=0
FAIL=0
GITHUB="https://github.com/mccoy88f/Tabloza-MidiExpander"
VERSION="?"
[[ -f /opt/tabloza/VERSION ]] && VERSION="$(tr -d '\n' < /opt/tabloza/VERSION)"

green()  { echo -e "\033[1;32m✓\033[0m $*"; OK=$((OK + 1)); }
yellow() { echo -e "\033[1;33m!\033[0m $*"; WARN=$((WARN + 1)); }
red()    { echo -e "\033[1;31m✗\033[0m $*"; FAIL=$((FAIL + 1)); }
hdr()    { echo ""; echo "── $* ──"; }

echo "╔══════════════════════════════════════════╗"
echo "║   Tabloza MidiExpander — Test v${VERSION}      ║"
echo "╚══════════════════════════════════════════╝"

# --- Sistema ---
hdr "Sistema"
echo "Hostname: $(hostname)"
echo "IP:       $(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Modello:  $(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo n/d)"

# --- Servizi ---
hdr "Servizi systemd"
for svc in tabloza-web tabloza-orchestrator tabloza-wifi rtpmidid avahi-daemon; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        green "$svc attivo"
    else
        red "$svc NON attivo — prova: sudo systemctl restart $svc"
    fi
done

# --- Web UI ---
hdr "Pannello web"
WEB_PORT=""
if ss -tlnp 2>/dev/null | grep -q ':80 '; then
    WEB_PORT=80
    green "Web UI in ascolto sulla porta 80"
elif ss -tlnp 2>/dev/null | grep -q ':8080 '; then
    WEB_PORT=8080
    yellow "Web UI sulla porta 8080 (aggiorna: sudo git -C /opt/tabloza pull && sudo systemctl restart tabloza-web)"
else
    red "Nessun server web su porta 80 o 8080"
fi

if [[ -n "$WEB_PORT" ]]; then
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${WEB_PORT}/" 2>/dev/null || echo "000")
  if [[ "$CODE" == "200" ]]; then
        green "HTTP test locale: 200 OK"
        IP=$(hostname -I | awk '{print $1}')
        echo "       → http://${IP}"
        echo "       → http://tabloza-me.local"
        [[ "$WEB_PORT" == "8080" ]] && echo "       → http://${IP}:8080"
    else
        red "HTTP test locale fallito (codice ${CODE})"
    fi
fi

# --- SoundFont ---
hdr "SoundFont"
DATA="/var/lib/tabloza"
if [[ -f "${DATA}/config.json" ]]; then
    ACTIVE=$(python3 -c "import json; print(json.load(open('${DATA}/config.json')).get('active_soundfont',''))" 2>/dev/null || true)
    COUNT=$(find "${DATA}/soundfonts" -name '*.sf2' 2>/dev/null | wc -l | tr -d ' ')
    if [[ -n "$ACTIVE" ]]; then
        green "SF2 attivo: ${ACTIVE}"
    elif [[ "$COUNT" -gt 0 ]]; then
        yellow "SF2 in libreria (${COUNT}) ma nessuno selezionato — carica dal pannello web"
    else
        yellow "Nessun SF2 — caricalo da http://$(hostname -I | awk '{print $1}')${WEB_PORT:+:${WEB_PORT}}"
    fi
else
    yellow "Config non trovata in ${DATA}"
fi

# --- RTP-MIDI ---
hdr "RTP-MIDI (rtpmidid)"
if command -v rtpmidid >/dev/null 2>&1; then
    green "rtpmidid installato: $(command -v rtpmidid)"
else
    red "rtpmidid non trovato"
fi

if [[ -f /etc/rtpmidid/default.ini ]]; then
    green "Config rtpmidid: /etc/rtpmidid/default.ini"
    grep -E '^(name|port)=' /etc/rtpmidid/default.ini 2>/dev/null | sed 's/^/       /' || true
else
    yellow "Manca /etc/rtpmidid/default.ini — Mac potrebbe non vedere il dispositivo"
    echo "       Fix: sudo bash /opt/tabloza/scripts/configure-rtpmidid.sh && sudo systemctl restart rtpmidid"
fi

if ss -ulnp 2>/dev/null | grep -q ':5004'; then
    green "UDP porta 5004 in ascolto (RTP-MIDI)"
else
    red "UDP 5004 non in ascolto — rtpmidid non annuncia su rete"
fi

if command -v avahi-browse >/dev/null 2>&1; then
    echo "       mDNS _apple-midi._udp (5s scan):"
    timeout 5 avahi-browse -r _apple-midi._udp 2>/dev/null | grep -E 'tabloza|hostname' | head -5 | sed 's/^/       /' || \
        yellow "Nessun annuncio Apple MIDI trovato via mDNS"
else
    yellow "avahi-browse non disponibile"
fi

# --- ALSA MIDI routing ---
hdr "Routing MIDI (ALSA)"
if command -v aconnect >/dev/null 2>&1; then
    echo "       Porte output (sorgenti):"
    aconnect -o 2>/dev/null | grep -iE 'fluidsynth|rtpmidid' | sed 's/^/       /' || yellow "Nessuna porta fluidsynth/rtpmidid"
    echo "       Porte input (destinazioni):"
    aconnect -i 2>/dev/null | grep -iE 'fluidsynth|rtpmidid' | sed 's/^/       /' || true
    if aconnect -o 2>/dev/null | grep -qi fluidsynth && aconnect -o 2>/dev/null | grep -qi rtpmidid; then
        green "FluidSynth e rtpmidid presenti in ALSA"
    else
        yellow "Routing incompleto — premi MIDI Reset nel pannello web"
    fi
else
    yellow "aconnect non disponibile"
fi

# --- Audio ---
hdr "Audio"
if pgrep -x fluidsynth >/dev/null 2>&1; then
    green "FluidSynth in esecuzione (PID $(pgrep -x fluidsynth))"
else
    red "FluidSynth non in esecuzione"
fi

# --- Mac / Windows ---
hdr "Come connettersi da Mac"
IP=$(hostname -I | awk '{print $1}')
cat <<EOF
  1. Stessa rete WiFi/LAN del Pi (${IP})
  2. macOS → Configurazione Audio e MIDI → Studio MIDI → Rete
  3. In "Le mie sessioni": clic + , attiva la sessione (spunta)
  4. In "Directory" cerca: tabloza-me
     Se non compare → Connetti manualmente a host: ${IP}  porta: 5004
  5. Nel DAW scegli uscita MIDI verso tabloza-me
  6. Verifica SF2 caricato e volume > 0 nel pannello web
EOF

# --- Riepilogo ---
hdr "Riepilogo"
echo "OK: ${OK}  Avvisi: ${WARN}  Errori: ${FAIL}"
echo "Repo: ${GITHUB}"
if [[ "$FAIL" -gt 0 ]]; then
    echo ""
    echo "Log utili:"
    echo "  sudo journalctl -u tabloza-web -u rtpmidid -u tabloza-orchestrator -n 30 --no-pager"
    exit 1
fi
exit 0

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
for svc in tabloza-web tabloza-orchestrator tabloza-wifi tabloza-midi-ws rtpmidid avahi-daemon; do
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
    green "Web UI HTTP in ascolto sulla porta 80"
elif ss -tlnp 2>/dev/null | grep -q ':443 '; then
    WEB_PORT=443
    yellow "Web UI HTTPS sulla porta 443 — esegui tabloza-update per HTTP :80"
elif ss -tlnp 2>/dev/null | grep -q ':8080 '; then
    WEB_PORT=8080
    yellow "Web UI sulla porta 8080 (versione obsoleta)"
else
    red "Nessun server web su porta 80, 443 o 8080"
    echo "       Log tabloza-web:"
    journalctl -u tabloza-web -n 8 --no-pager 2>/dev/null | sed 's/^/       /' || true
    echo "       → sudo systemctl restart tabloza-web"
fi

if [[ -n "$WEB_PORT" ]]; then
    if [[ "$WEB_PORT" == "443" ]]; then
        CODE=$(curl -sk -o /dev/null -w "%{http_code}" "https://127.0.0.1:${WEB_PORT}/" 2>/dev/null || echo "000")
        if [[ "$CODE" == "200" ]]; then
            green "HTTPS test locale: 200 OK"
            IP=$(hostname -I | awk '{print $1}')
            echo "       → https://${IP}"
            echo "       → https://tabloza-me.local"
        else
            red "HTTPS test locale fallito (codice ${CODE})"
        fi
    else
        CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${WEB_PORT}/" 2>/dev/null || echo "000")
        if [[ "$CODE" == "200" || "$CODE" == "301" ]]; then
            green "HTTP test locale: ${CODE}"
            IP=$(hostname -I | awk '{print $1}')
            echo "       → http://${IP}"
            echo "       → http://tabloza-me.local"
        else
            red "HTTP test locale fallito (codice ${CODE})"
        fi
    fi
fi

# --- WebSocket MIDI (Tabloza Sing) ---
hdr "WebSocket MIDI (WSS :8765)"
if ss -tlnp 2>/dev/null | grep -q ':8765 '; then
    green "Porta 8765 in ascolto"
    if command -v openssl >/dev/null; then
        if timeout 3 openssl s_client -connect 127.0.0.1:8765 -servername tabloza-me.local </dev/null 2>/dev/null | grep -q "BEGIN CERTIFICATE"; then
            green "TLS/WSS attivo su 8765"
            echo "       → https://tabloza-me.local:8765/setup"
        else
            yellow "Porta 8765 aperta ma TLS assente — esegui sudo tabloza-update"
        fi
    fi
else
    red "Nessun servizio su porta 8765 — sudo systemctl status tabloza-midi-ws"
    journalctl -u tabloza-midi-ws -n 6 --no-pager 2>/dev/null | sed 's/^/       /' || true
fi

# --- SoundFont ---
hdr "SoundFont"
DATA="/var/lib/tabloza"
if [[ -f "${DATA}/config.json" ]]; then
    ACTIVE=$(python3 -c "import json; print(json.load(open('${DATA}/config.json')).get('active_soundfont',''))" 2>/dev/null || true)
    LOADED=$(python3 -c "import json; print(json.load(open('/run/tabloza/soundfont_state.json')).get('loaded',''))" 2>/dev/null || true)
    LOADING=$(python3 -c "import json; print(json.load(open('/run/tabloza/soundfont_state.json')).get('loading',False))" 2>/dev/null || true)
    COUNT=$(find "${DATA}/soundfonts" -name '*.sf2' 2>/dev/null | wc -l | tr -d ' ')
    if [[ -n "$LOADED" ]]; then
        green "SF2 caricato in FluidSynth: ${LOADED}"
    elif [[ "$LOADING" == "True" ]]; then
        yellow "SF2 in caricamento: ${ACTIVE:-?}"
    elif [[ -n "$ACTIVE" ]]; then
        yellow "SF2 selezionato ma non caricato: ${ACTIVE} — premi Carica nel pannello web"
    elif [[ "$COUNT" -gt 0 ]]; then
        yellow "SF2 in libreria (${COUNT}) — seleziona e carica dal pannello web"
    else
        yellow "Nessun SF2 — caricalo da http://$(hostname -I | awk '{print $1}')"
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
    MDNS_OUT=$(timeout 5 avahi-browse -r _apple-midi._udp 2>/dev/null || true)
    if echo "$MDNS_OUT" | grep -qi tabloza; then
        echo "$MDNS_OUT" | grep -iE 'tabloza|hostname' | head -5 | sed 's/^/       /'
        TABLOZA_COUNT=$(echo "$MDNS_OUT" | grep -ci 'tabloza-me' || true)
        if [[ "$TABLOZA_COUNT" -gt 2 ]]; then
            yellow "Più annunci tabloza-me (atteso: 1) — esegui tabloza-update e riavvia rtpmidid"
        else
            green "Annuncio tabloza-me su mDNS"
        fi
        if echo "$MDNS_OUT" | grep -qi 'fluid synth'; then
            yellow "FluidSynth annunciato in rete (non dovrebbe) — verifica /etc/rtpmidid/default.ini"
        fi
    else
        yellow "Nessun annuncio Apple MIDI trovato via mDNS"
    fi
else
    yellow "avahi-browse non disponibile"
fi

# --- ALSA MIDI routing ---
hdr "Routing MIDI (ALSA)"
if command -v aconnect >/dev/null 2>&1; then
    echo "       Porte output (sorgenti):"
    aconnect -o 2>/dev/null | grep -iE 'fluid|rtpmidid' | sed 's/^/       /' || yellow "Nessuna porta fluid/rtpmidid"
    echo "       Porte input (destinazioni):"
    aconnect -i 2>/dev/null | grep -iE 'fluid|rtpmidid' | sed 's/^/       /' || true
    if aconnect -i 2>/dev/null | grep -qi fluid && aconnect -o 2>/dev/null | grep -qi rtpmidid; then
        green "FluidSynth e rtpmidid presenti in ALSA"
    else
        yellow "Routing incompleto — premi MIDI Reset nel pannello web"
    fi
else
    yellow "aconnect non disponibile"
fi

# --- Audio ---
hdr "Audio"
FS_ALIVE=0
while read -r pid; do
    [[ -z "$pid" ]] && continue
    state=$(awk '/^State:/{print $2}' "/proc/${pid}/status" 2>/dev/null || echo "")
    if [[ "$state" == "Z" ]]; then
        yellow "FluidSynth zombie (PID ${pid}) — riavvia: sudo systemctl restart tabloza-orchestrator"
        continue
    fi
    line=$(ps -p "$pid" -o args= 2>/dev/null || true)
    echo "       ${pid} ${line}"
    if [[ "$line" == *"midi.autoconnect=false"* ]] || [[ "$line" == *"midi.autoconnect false"* ]] || [[ "$line" == *"synth.default-soundfont"* ]] || [[ "$line" == *"/var/lib/tabloza/soundfonts/"* ]]; then
        FS_ALIVE=$((FS_ALIVE + 1))
    elif [[ "$line" == *fluidsynth* ]]; then
        yellow "FluidSynth di sistema in conflitto — arrestalo:"
        echo "       sudo systemctl mask fluidsynth; sudo kill ${pid}"
    fi
done < <(pgrep -x fluidsynth 2>/dev/null || true)
if [[ "$FS_ALIVE" -gt 0 ]]; then
    green "FluidSynth Tabloza attivo"
elif pgrep -x fluidsynth >/dev/null 2>&1; then
    yellow "Nessun FluidSynth Tabloza valido in esecuzione"
else
    red "FluidSynth non in esecuzione"
fi

if command -v aplay >/dev/null 2>&1; then
    echo "       Dispositivi ALSA playback:"
    aplay -l 2>/dev/null | sed 's/^/       /' || yellow "aplay -l fallito"
else
    yellow "aplay non disponibile"
fi

PCM_RUNNING=false
for st in /proc/asound/card*/pcm*p/sub*/status; do
  if [[ -f "$st" ]] && grep -q "state: RUNNING" "$st" 2>/dev/null; then
    PCM_RUNNING=true
    echo "       PCM attivo: $st"
  fi
done
if $PCM_RUNNING; then
    green "ALSA playback in stato RUNNING (audio in uscita)"
else
    yellow "Nessun PCM in RUNNING — normale se silenzio; suona una nota e riprova"
fi

if [[ -f /var/lib/tabloza/config.json ]]; then
    SF=$(python3 -c "import json; print(json.load(open('/var/lib/tabloza/config.json')).get('active_soundfont',''))" 2>/dev/null || true)
    VOL=$(python3 -c "import json; print(json.load(open('/var/lib/tabloza/config.json')).get('volume',100))" 2>/dev/null || true)
    echo "       SF2 attivo: ${SF:-nessuno}  Volume: ${VOL:-?}"
    [[ -n "$SF" && -f "/var/lib/tabloza/soundfonts/$SF" ]] && green "File SF2 presente" || yellow "SF2 mancante o non selezionato"
fi

echo "       Test hardware jack (1 ciclo beep, Ctrl+C per saltare):"
echo "       →  speaker-test -t wav -c 2 -l 1"
echo "       Test nota FluidSynth:"
FS_ADDR=$(python3 -c "
import sys
sys.path.insert(0, '/opt/tabloza/src')
from midi_utils import find_fluidsynth_input
p = find_fluidsynth_input()
print(p['address'] if p else '')
" 2>/dev/null || true)
if [[ -n "$FS_ADDR" ]]; then
    echo "       Porta FluidSynth: $FS_ADDR"
    SF_LOADED=$(python3 -c "import json; print(json.load(open('/run/tabloza/soundfont_state.json')).get('loaded',''))" 2>/dev/null || true)
    if [[ -n "$SF_LOADED" ]]; then
        if systemctl kill -s USR1 tabloza-orchestrator 2>/dev/null; then
            sleep 0.5
            green "Nota di test richiesta via orchestrator (SIGUSR1)"
        else
            yellow "Impossibile inviare SIGUSR1 all'orchestrator"
        fi
    else
        yellow "Nessun SoundFont caricato — premi Carica nel pannello web prima del test suono"
    fi
else
    yellow "Porta input FluidSynth non trovata"
    if [[ -f /run/tabloza/fluidsynth.log ]]; then
        echo "       Ultimo log FluidSynth:"
        tail -8 /run/tabloza/fluidsynth.log | sed 's/^/       /'
        echo "       → sudo journalctl -u tabloza-orchestrator -n 20 --no-pager"
    fi
fi

if [[ -f /run/tabloza/last_midi_event ]]; then
    AGO=$(python3 -c "import time; print(round(time.time()-float(open('/run/tabloza/last_midi_event').read()),1))" 2>/dev/null || echo "?")
    echo "       Ultimo evento MIDI: ${AGO}s fa (monitor orchestrator)"
fi

# --- Mac / Windows ---
hdr "Come connettersi da Mac"
IP=$(hostname -I | awk '{print $1}')
cat <<EOF
  1. Stessa rete WiFi/LAN del Pi (${IP})
  2. macOS Sequoia/Tahoe: Configurazione Audio e MIDI → Finestra → Configura driver di rete
     (macOS vecchi: Studio MIDI → doppio clic Rete)
  3. Sessione RTP con + , attiva la spunta
  4. Directory → tabloza-me (o manuale: ${IP}:5004)
  5. Nel DAW: uscita MIDI verso tabloza-me
  6. Pannello web: MIDI in / Audio out + pulsante Test suono
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

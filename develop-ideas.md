# Tabloza MidiExpander — Specifica di Progetto

> Repository: https://github.com/mccoy88f/Tabloza-MidiExpander

## 1. Panoramica

Sintetizzatore MIDI headless basato su **Raspberry Pi** con Raspberry Pi OS Lite **64-bit**.
Il dispositivo riceve MIDI da **RTP-MIDI di rete** (attivo) e in futuro da **porta MIDI IN fisica (GPIO UART)** — vedi [docs/TODO.md](docs/TODO.md).

Tutto è gestibile da **interfaccia web responsive** (smartphone): upload/selezione SF2, monitoraggio connettività, volume master, configurazione WiFi.

### Hardware supportato

| Modello | Supporto |
|---------|----------|
| Raspberry Pi 4 | ✅ Target principale |
| Raspberry Pi 5 | ✅ Target principale |
| Raspberry Pi 3 | ⚠️ Supporto limitato (latenza audio superiore, prestazioni ridotte con SF2 grandi) |

---

## 2. Installazione

**Prerequisito:** Raspberry Pi OS Lite 64-bit già installato e accesso terminale (SSH o locale).

**Una sola riga:**

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

Lo script:
1. Verifica Pi OS 64-bit e architettura ARM
2. Installa dipendenze di sistema
3. Installa e configura `rtpmidid`, FluidSynth, NetworkManager
4. Deploya servizi systemd e applicazione web
5. Imposta hostname `tabloza-me` (mDNS: `tabloza-me.local`)
6. Imposta password predefinita, secret key e dati persistenti
7. Riavvia i servizi (reboot consigliato al termine)

> MIDI GPIO UART: pianificato, non attivo all'install. Script pronto in `scripts/configure-midi-uart.sh`.

---

## 3. Architettura di Rete (Captive-Ready)

Dispositivo headless: la resilienza di rete è critica.

### Flusso WiFi al boot

1. **Profili noti:** NetworkManager cerca reti WiFi salvate
2. **Connessione client:** se trovata, tenta connessione (timeout 20 s)
3. **Fallback hotspot:** se nessuna rete o connessione fallita → Access Point automatico
   - SSID: `Tabloza-MidiExpander`
   - IP fisso: `192.168.4.1`
   - DHCP attivo per smartphone/tablet
4. **Provisioning via Web UI:** dall'hotspot l'utente scansiona reti, inserisce password, salva profilo per boot successivi

### Identità di rete

- **Hostname / mDNS:** `tabloza-me.local`
- **RTP-MIDI:** visibile come `tabloza-me` via Avahi/mDNS
- **Monitor WiFi:** servizio continuo con riconnessione/hotspot ogni 30 s

---

## 4. Hardware e I/O

### MIDI fisico (GPIO) — PIANIFICATO

> Stato: **non implementato**. Vedi `docs/TODO.md`.

- **UART:** GPIO 14 (TX), GPIO 15 (RX)
- **Baud rate:** 31250 bps (`scripts/configure-midi-uart.sh` pronto ma non eseguito)
- **Isolamento:** optoisolatore MIDI standard (es. 6N138) su RX

### MIDI di rete (RTP-MIDI)

- **Daemon:** `rtpmidid` (scelta definitiva)
- **Discovery:** Avahi/mDNS per iOS, macOS, Windows (rtpMIDI)

### Audio

- **Engine:** FluidSynth con driver ALSA
- **Output:** jack analogico integrato (`plughw:0,0` su Pi 4/5)
- **Ottimizzazioni:** buffer `-p`/`-c` tunati, `rtprio` per thread audio

---

## 5. Sicurezza

- **Autenticazione web:** password obbligatoria su tutte le API e sulla dashboard
- **Password predefinita:** `tabloza` (cambiabile dall'interfaccia web → Impostazioni → Sicurezza)
- **Storage:** hash bcrypt in `/var/lib/tabloza/auth.json` (persistente)
- **Hotspot:** rete aperta per provisioning iniziale; dopo configurazione WiFi il dispositivo passa in modalità client

---

## 6. Persistenza

Tutto lo stato utente sopravvive a reboot e power-off:

| Dato | Percorso |
|------|----------|
| SoundFont attivo | `/var/lib/tabloza/config.json` |
| Volume master | `/var/lib/tabloza/config.json` |
| Libreria SF2 | `/var/lib/tabloza/soundfonts/` |
| Password (hash) | `/var/lib/tabloza/auth.json` |
| Profili WiFi | NetworkManager (`/etc/NetworkManager/`) |

---

## 7. Strategia filesystem (read-only root)

**Scelta:** filesystem root in **lettura/scrittura** (default Raspberry Pi OS).

Motivazione:
- Installazione one-liner senza overlayfs complessi
- Upload SF2, cambio password e profili WiFi richiedono scrittura
- Aggiornamenti via `git pull` + reinstall semplificati

**Resilienza agli spegnimenti bruschi:**
- Dati applicativi isolati in `/var/lib/tabloza/` (ext4 con journal)
- Servizi systemd con `Restart=always` e `WatchdogSec`
- Configurazione UART in `/boot/firmware/` (partizione separata)

> Read-only root con overlayfs documentato come ottimizzazione avanzata opzionale nel README.

---

## 8. Stack software

### Fase 1 — Orchestratore MIDI/Audio

Daemon Python `midi_orchestrator.py` (systemd: `tabloza-orchestrator.service`):
- Avvia FluidSynth con SF2 attivo
- `aconnect` automatico: seriale hardware + porte virtuali `rtpmidid` → FluidSynth
- Hot-reload su cambio SoundFont (SIGHUP)

### Fase 2 — Backend API (Python/Flask)

Servizio `tabloza-web.service`:
- `GET /api/soundfonts` — lista SF2 + attivo
- `POST /api/soundfonts/select` — cambia SF2, reload orchestratore
- `POST /api/soundfonts/upload` — upload multipart
- `DELETE /api/soundfonts/<name>` — elimina SF2
- `POST /api/volume` — volume master (MIDI CC 7)
- `GET /api/wifi/scan` — scan reti (`nmcli`)
- `POST /api/wifi/connect` — salva credenziali WiFi
- `GET /api/status` — IP, modalità rete, connessioni (sorgenti + synth)
- `POST /api/auth/change-password` — cambio password

### Fase 3 — Frontend Dashboard

SPA responsive (HTML5 + Vanilla JS):
1. Login
2. Status bar (IP, hotspot/client, connections)
3. Libreria SoundFont (carica/elimina)
4. Upload drag-and-drop con progress
5. Slider volume master
6. Pannello WiFi provisioning
7. Impostazioni sicurezza (cambio password)

---

## 9. Servizi systemd

| Servizio | Ruolo |
|----------|-------|
| `tabloza-wifi.service` | Gestione hotspot fallback al boot |
| `rtpmidid.service` | RTP-MIDI network daemon |
| `tabloza-orchestrator.service` | FluidSynth + routing MIDI |
| `tabloza-web.service` | API Flask + frontend statico |

---

## 10. Principi di sviluppo

1. **Low latency first** — ALSA, FluidSynth, `rtprio`
2. **Codice production-ready** — niente placeholder
3. **Resilienza** — systemd restart, dati persistenti isolati
4. **Installazione zero-friction** — una riga dopo Pi OS 64-bit

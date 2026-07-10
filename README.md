# Tabloza MidiExpander

**[Italiano](#italiano)** · **[English](#english)**

Trasforma un Raspberry Pi in un expander MIDI headless con sintesi SoundFont, RTP-MIDI e pannello web da smartphone.

Turns a Raspberry Pi into a headless MIDI expander with SoundFont synthesis, RTP-MIDI, and a smartphone-friendly web panel.

---

## Italiano

### Cos'è Tabloza MidiExpander

Tabloza MidiExpander è un **sintetizzatore MIDI standalone** basato su Raspberry Pi. Il dispositivo funziona **senza schermo e senza tasti**: tutto si controlla da browser (smartphone o PC) tramite una interfaccia web responsive.

Riceve note MIDI via **RTP-MIDI di rete** (compatibile con iOS, macOS e Windows) e le trasforma in audio in tempo reale usando **FluidSynth** e file SoundFont (`.sf2`), con uscita sul jack audio analogico del Pi.

> **MIDI GPIO fisico** (porta DIN su GPIO 14/15): funzione pianificata, non ancora attiva. Vedi [docs/TODO.md](docs/TODO.md).

### Funzionalità

| Funzione | Descrizione |
|----------|-------------|
| **Sintesi SF2** | FluidSynth con libreria SoundFont gestibile da web |
| **RTP-MIDI** | Visibile in rete come `tabloza-me.local` (rtpmidid + Avahi) |
| **Pannello web** | UI responsive in italiano e inglese |
| **Upload SF2** | Drag-and-drop con barra di progresso; auto-attivazione |
| **Volume master** | Persistente tra reboot |
| **WiFi provisioning** | Hotspot automatico → configurazione rete domestica |
| **Monitor WiFi** | Riconnessione automatica se la rete cade |
| **MIDI Reset** | Riavvio FluidSynth e routing MIDI con un click |
| **Sicurezza** | Login con password (default: `tabloza`) |

### Interfaccia web (UI)

Accesso: **http://tabloza-me.local** (o `http://192.168.4.1` in modalità hotspot)

La UI è **bilingue** (IT/EN): usa i pulsanti **IT** / **EN** in alto. La lingua scelta viene salvata nel browser.

| Sezione | Cosa fa |
|---------|---------|
| **Stato** | Indirizzo mDNS, IP, modalità rete, SF2 attivo, ingressi MIDI |
| **MIDI Reset** | Riavvia rtpmidid + FluidSynth in caso di problemi |
| **Volume Master** | Slider 0–127, salvato automaticamente |
| **Libreria SoundFont** | Lista, carica, elimina, upload `.sf2` |
| **WiFi** | Scan reti, inserimento password, salvataggio profilo |
| **Sicurezza** | Cambio password |

### Requisiti

- Raspberry Pi **4 o 5** (consigliato) — Pi 3 supporto limitato
- **Raspberry Pi OS Lite 64-bit**
- Accesso terminale (SSH o locale)

### Installazione

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
sudo reboot
```

### Primo accesso

1. Connettiti alla rete del dispositivo o all'hotspot `Tabloza-MidiExpander`
2. Apri **http://tabloza-me.local** (o `http://<IP-del-Pi>`)
3. Password: `tabloza`

### Configurazione RTP-MIDI wireless

Il Pi annuncia una sessione RTP-MIDI sulla rete:
- **Nome:** `tabloza-me`
- **Porta UDP:** `5004`
- **mDNS:** `tabloza-me.local`

Prerequisiti sul Pi: carica un file `.sf2` dal pannello web e verifica con `sudo tabloza-test`.

#### macOS / iOS

1. Mac e Pi sulla **stessa rete WiFi/LAN**
2. Apri **Configurazione Audio e MIDI** → **Finestra → Mostra Studio MIDI**
3. **macOS Sequoia / Tahoe (15+):** **Finestra → Configura driver di rete** (non più doppio clic su Rete)
   - **macOS più vecchi:** doppio clic sull'icona **Rete** (globo)
4. Crea una sessione **RTP** (pulsante **+** in «Le mie sessioni») e attiva la spunta
5. In **Directory** cerca **`tabloza-me`** → **Connetti**
6. Se non compare: **Connetti manualmente** con host `tabloza-me.local` (o IP del Pi) porta **5004**
7. Nel DAW: uscita MIDI verso `tabloza-me`

Verifica discovery dal Mac:
```bash
dns-sd -B _apple-midi._udp
# oppure
dns-sd -L tabloza-me _apple-midi._udp
```

#### Windows

1. Installa [rtpMIDI](https://www.tobias-erichsen.de/software/rtpmidi.html)
2. (Consigliato) Installa [Bonjour](https://support.apple.com/kb/DL999) per la scoperta `.local`
3. Avvia rtpMIDI → cerca **`tabloza-me`** → **Connect**
4. Connessione manuale: host = IP del Pi, porta = **5004**

#### Se non suona

Nel **pannello web** (sezione Stato):
- **MIDI in** lampeggia verde quando arrivano note dal Mac
- **Audio out** lampeggia quando FluidSynth sta effettivamente riproducendo
- **Test suono** invia un Do direttamente al synth (bypassa RTP-MIDI)
- Verifica SF2 attivo, volume > 0, badge **Collegato** su rtpmidid

**Test rapidi SSH sul Pi:**

```bash
# 1. Diagnostica completa
sudo tabloza-test

# 2. Hardware jack audio (dovresti sentire un beep)
speaker-test -t wav -c 2 -l 1

# 3. FluidSynth e routing MIDI
pgrep -a fluidsynth
aconnect -l | grep -E 'fluidsynth|rtpmidid|Connected'

# 4. Nota di test diretta (senza Mac)
FS=$(aconnect -i | grep -i fluidsynth | head -1 | awk '{print $2}')
sudo amidi -p "$FS" -S "90 3C 64" && sleep 0.3 && sudo amidi -p "$FS" -S "80 3C 00"

# 5. Log in tempo reale mentre suoni dal Mac
sudo journalctl -u tabloza-orchestrator -f
```

**Interpretazione:**
| Test suono (web) | MIDI in (web) | Probabile causa |
|------------------|---------------|-----------------|
| Si sente | No lampeggia | Mac non invia MIDI o routing RTP → FluidSynth rotto → **MIDI Reset** |
| Non si sente | — | Problema audio ALSA / jack / SF2 → `speaker-test`, verifica SF2 |
| Si sente | Lampeggia | Audio OK, controlla volume Mac/DAW e canale MIDI |

- Pannello web → **MIDI Reset** dopo ogni nuova connessione Mac
- SSH: `sudo systemctl restart tabloza-orchestrator rtpmidid`

### Comandi utili (SSH)

```bash
sudo tabloza-test          # diagnostica completa
sudo systemctl restart tabloza-web tabloza-orchestrator rtpmidid
```

### Disinstallazione e reinstallazione pulita

**Se hai già una versione precedente** e vuoi ripartire da zero:

```bash
# 1. Disinstalla (se il comando esiste)
sudo tabloza-uninstall

# Se tabloza-uninstall non esiste ancora, disinstalla manualmente:
sudo systemctl stop tabloza-web tabloza-orchestrator tabloza-wifi rtpmidid
sudo systemctl disable tabloza-web tabloza-orchestrator tabloza-wifi rtpmidid
sudo rm -f /etc/systemd/system/tabloza-*.service /etc/systemd/system/rtpmidid.service
sudo rm -rf /opt/tabloza /etc/rtpmidid
sudo rm -f /etc/avahi/services/tabloza-web.service
sudo systemctl daemon-reload

# 2. (Opzionale) Elimina anche SF2 e password salvate
sudo rm -rf /var/lib/tabloza

# 3. Reinstalla
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
sudo reboot

# 4. Verifica
sudo tabloza-test
```

Durante `tabloza-uninstall` puoi scegliere se eliminare anche `/var/lib/tabloza` (SF2, password).

### Dati persistenti

```
/var/lib/tabloza/
├── config.json      # SoundFont attivo, volume
├── auth.json        # hash password
├── secret.key       # secret key Flask
└── soundfonts/      # libreria .sf2
```

### Servizi

```bash
sudo systemctl status tabloza-web tabloza-orchestrator tabloza-wifi rtpmidid
```

### Troubleshooting

Vedi [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### Aggiornamento

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

---

## English

### What is Tabloza MidiExpander

Tabloza MidiExpander is a **standalone MIDI synthesizer** built on Raspberry Pi. The device runs **headless** (no screen, no buttons): everything is controlled from a browser (smartphone or PC) via a responsive web interface.

It receives MIDI over **network RTP-MIDI** (compatible with iOS, macOS, and Windows) and renders real-time audio using **FluidSynth** and SoundFont (`.sf2`) files, outputting to the Pi's analog audio jack.

> **Physical GPIO MIDI** (DIN port on GPIO 14/15): planned feature, not yet active. See [docs/TODO.md](docs/TODO.md).

### Features

| Feature | Description |
|---------|-------------|
| **SF2 synthesis** | FluidSynth with web-managed SoundFont library |
| **RTP-MIDI** | Discoverable as `tabloza-me.local` (rtpmidid + Avahi) |
| **Web panel** | Responsive UI in Italian and English |
| **SF2 upload** | Drag-and-drop with progress bar; auto-activation |
| **Master volume** | Persists across reboots |
| **WiFi provisioning** | Automatic hotspot → home network setup |
| **WiFi monitor** | Auto-reconnect if network drops |
| **MIDI Reset** | Restart FluidSynth and MIDI routing in one click |
| **Security** | Password login (default: `tabloza`) |

### Web interface (UI)

Access: **http://tabloza-me.local** (or `http://192.168.4.1` in hotspot mode)

The UI is **bilingual** (IT/EN): use the **IT** / **EN** buttons at the top. Language preference is saved in the browser.

| Section | Purpose |
|---------|---------|
| **Status** | mDNS address, IP, network mode, active SF2, MIDI inputs |
| **MIDI Reset** | Restart rtpmidid + FluidSynth when troubleshooting |
| **Master Volume** | Slider 0–127, auto-saved |
| **SoundFont Library** | List, load, delete, upload `.sf2` files |
| **WiFi** | Scan networks, enter password, save profile |
| **Security** | Change password |

### Requirements

- Raspberry Pi **4 or 5** (recommended) — Pi 3 limited support
- **Raspberry Pi OS Lite 64-bit**
- Terminal access (SSH or local)

### Installation

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
sudo reboot
```

### First access

1. Connect to the device network or hotspot `Tabloza-MidiExpander`
2. Open **http://tabloza-me.local** (or `http://<Pi-IP>`)
3. Password: `tabloza`

### Wireless RTP-MIDI setup

The Pi advertises an RTP-MIDI session on the network:
- **Name:** `tabloza-me`
- **UDP port:** `5004`
- **mDNS:** `tabloza-me.local`

Prerequisites on the Pi: upload a `.sf2` via the web panel and run `sudo tabloza-test`.

#### macOS / iOS

1. Mac and Pi on the **same WiFi/LAN**
2. Open **Audio MIDI Setup** → **Window → Show MIDI Studio**
3. **macOS Sequoia / Tahoe (15+):** **Window → Configure Network Driver** (no longer double-click Network)
   - **Older macOS:** double-click the **Network** globe icon
4. Create an **RTP** session (**+** under My Sessions) and enable the checkbox
5. Under **Directory** find **`tabloza-me`** → **Connect**
6. If missing: connect manually to host `tabloza-me.local` (or Pi IP) port **5004**
7. In your DAW: MIDI output to `tabloza-me`

Verify discovery from the Mac:
```bash
dns-sd -B _apple-midi._udp
# or
dns-sd -L tabloza-me _apple-midi._udp
```

#### Windows

1. Install [rtpMIDI](https://www.tobias-erichsen.de/software/rtpmidi.html)
2. (Recommended) Install [Bonjour](https://support.apple.com/kb/DL999) for `.local` discovery
3. Launch rtpMIDI → find **`tabloza-me`** → **Connect**
4. Manual connection: host = Pi IP, port = **5004**

#### No sound?

In the **web panel** (Status section):
- **MIDI in** pulses green when notes arrive from the Mac
- **Audio out** pulses when FluidSynth is actually playing
- **Sound test** sends middle C directly to the synth (bypasses RTP-MIDI)
- Check active SF2, volume > 0, **Connected** badge on rtpmidid

**Quick SSH tests on the Pi:**

```bash
sudo tabloza-test
speaker-test -t wav -c 2 -l 1
pgrep -a fluidsynth
aconnect -l | grep -E 'fluidsynth|rtpmidid|Connected'
FS=$(aconnect -i | grep -i fluidsynth | head -1 | awk '{print $2}')
sudo amidi -p "$FS" -S "90 3C 64" && sleep 0.3 && sudo amidi -p "$FS" -S "80 3C 00"
sudo journalctl -u tabloza-orchestrator -f
```

| Web sound test | MIDI in (web) | Likely cause |
|----------------|---------------|--------------|
| Heard | No pulse | Mac not sending MIDI or RTP → FluidSynth routing broken → **MIDI Reset** |
| Silent | — | ALSA / jack / SF2 issue → `speaker-test`, check SF2 |
| Heard | Pulsing | Audio OK — check Mac/DAW volume and MIDI channel |

- Web panel → **MIDI Reset** after each new Mac connection
- SSH: `sudo systemctl restart tabloza-orchestrator rtpmidid`

### Useful commands (SSH)

```bash
sudo tabloza-test          # full diagnostics
sudo systemctl restart tabloza-web tabloza-orchestrator rtpmidid
```

### Uninstall and clean reinstall

**If you have a previous version** and want a fresh start:

```bash
# 1. Uninstall (if command exists)
sudo tabloza-uninstall

# If tabloza-uninstall is not available yet, remove manually:
sudo systemctl stop tabloza-web tabloza-orchestrator tabloza-wifi rtpmidid
sudo systemctl disable tabloza-web tabloza-orchestrator tabloza-wifi rtpmidid
sudo rm -f /etc/systemd/system/tabloza-*.service /etc/systemd/system/rtpmidid.service
sudo rm -rf /opt/tabloza /etc/rtpmidid
sudo rm -f /etc/avahi/services/tabloza-web.service
sudo systemctl daemon-reload

# 2. (Optional) Delete saved SF2 and password
sudo rm -rf /var/lib/tabloza

# 3. Reinstall
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
sudo reboot

# 4. Verify
sudo tabloza-test
```

During `tabloza-uninstall` you can choose whether to delete `/var/lib/tabloza` (SF2, password).

### Persistent data

```
/var/lib/tabloza/
├── config.json      # active SoundFont, volume
├── auth.json        # password hash
├── secret.key       # Flask secret key
└── soundfonts/      # .sf2 library
```

### Services

```bash
sudo systemctl status tabloza-web tabloza-orchestrator tabloza-wifi rtpmidid
```

### Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### Update

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

Data in `/var/lib/tabloza/` is preserved.

---

## License / Licenza

MIT

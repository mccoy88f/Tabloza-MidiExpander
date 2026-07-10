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
2. Apri **http://tabloza-me.local**
3. Password: `tabloza`

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
2. Open **http://tabloza-me.local**
3. Password: `tabloza`

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

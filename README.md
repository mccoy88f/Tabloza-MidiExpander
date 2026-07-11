# Tabloza MidiExpander

**Italiano** · **[English](README-en.md)**

Trasforma un Raspberry Pi in un expander MIDI headless con sintesi SoundFont, RTP-MIDI e pannello web da smartphone.

---

### Cos'è Tabloza MidiExpander

Tabloza MidiExpander è un **sintetizzatore MIDI standalone** basato su Raspberry Pi. Il dispositivo funziona **senza schermo e senza tasti**: tutto si controlla da browser (smartphone o PC) tramite una interfaccia web responsive.

Riceve note MIDI via **RTP-MIDI di rete** (compatibile con iOS, macOS e Windows) e, in parallelo, da **dongle USB‑MIDI** collegato al Pi. L’audio usa **FluidSynth** e file SoundFont (`.sf2`), con uscita configurabile (jack, USB, HDMI).

> **Sviluppi futuri:** ingresso **MIDI GPIO** (porta DIN su UART GPIO 14/15 + optoisolatore) — non ancora implementato. Dettagli in [docs/TODO.md](docs/TODO.md).

### Funzionalità

| Funzione | Descrizione |
|----------|-------------|
| **Sintesi SF2** | FluidSynth con libreria SoundFont gestibile da web |
| **Motore synth** | Preset buffer, polifonia, riverbero, chorus, caricamento dinamico SF2 |
| **Uscita audio** | Selezione dispositivo ALSA (jack integrato, USB, HDMI) con volume in percentuale |
| **RTP-MIDI** | Visibile in rete come `tabloza-me.local` (rtpmidid + Avahi) |
| **MIDI USB** | Dongle/interfaccia USB‑MIDI sul Pi, routing automatico in parallelo alla rete |
| **Pannello web** | UI responsive bilingue (IT/EN), sezioni espandibili |
| **Upload SF2** | Drag-and-drop con barra di progresso (max 2 GB); attivazione manuale o automatica |
| **Rete adattiva** | Ethernet, WiFi client, hotspot, link LAN diretto; UI che mostra solo le opzioni pertinenti |
| **Link LAN diretto** | Cavo Pi ↔ computer senza router: DHCP automatico su `192.168.5.1` |
| **WiFi provisioning** | Hotspot `Tabloza-MidiExpander` se non c’è rete; connessione a reti domestiche |
| **Monitor rete** | Riconnessione WiFi, fallback hotspot, gestione automatica Ethernet |
| **Diagnostica** | RAM, CPU, disco, temperatura, console eventi e verifica aggiornamenti |
| **MIDI Reset** | Riavvio FluidSynth e routing MIDI con un click |
| **Sicurezza** | Login con password (default: `tabloza`) |

### Interfaccia web (UI)

Accesso: **http://tabloza-me.local** (o l’IP mostrato in Stato)

La UI è **bilingue** (IT/EN): usa i pulsanti **IT** / **EN** in alto. La lingua scelta viene salvata nel browser.

| Sezione | Cosa fa |
|---------|---------|
| **Stato** | Indirizzo mDNS, IP per interfaccia, modalità rete `Ethernet + WiFi (nome)`, SF2, versione, **ingressi MIDI**, test suono/jack, MIDI Reset |
| **Volume uscita audio** | Slider **0–100%**, salvato automaticamente |
| **Uscita audio** | Elenco dispositivi ALSA playback; cambio uscita (jack, USB, HDMI…) con riavvio synth |
| **Motore synth** | Preset buffer, polifonia, riverbero, chorus, caricamento dinamico; *Stop note* |
| **Libreria SoundFont** | Lista, carica, elimina, upload `.sf2` |
| **Rete** | Badge modalità attiva; link LAN diretto, hotspot e WiFi client (mostrati in base allo stato) |
| **Diagnostica** | Metriche sistema (RAM, CPU, disco, temperatura), verifica aggiornamenti, console eventi |
| **Sicurezza** | Cambio password (sezione collassabile) |

### Modalità di rete

Il pannello rileva automaticamente la connettività e adatta i controlli disponibili.

| Modalità (Stato) | Significato |
|------------------|-------------|
| **Ethernet** | Solo cavo LAN al router |
| **WiFi (*nome rete*)** | Solo WiFi client |
| **Ethernet + WiFi (*nome rete*)** | Cavo e WiFi client attivi insieme |
| **Hotspot** | Pi emette `Tabloza-MidiExpander` (es. primo avvio o senza rete) |
| **Link LAN diretto** | Cavo diretto Pi ↔ computer, Pi @ `192.168.5.1` |
| **Offline** | Nessuna connessione utile |

**IP in Stato:** con più interfacce attive vengono mostrati entrambi, es. `192.168.178.143 (Ethernet) · 192.168.178.50 (WiFi)`.

**Ethernet con router:** il Pi tenta prima il DHCP normale. Se il cavo è collegato ma non arriva IP entro ~25 s (es. link diretto a un computer), passa automaticamente al **link LAN diretto** (`192.168.5.1`, DHCP sul cavo). Puoi forzare avvio/stop dal pannello.

**Hotspot:** parte automaticamente se non c’è Ethernet né WiFi configurato; puoi avviarlo/fermarlo manualmente quando non sei su LAN router. Con cavo al router, l’hotspot resta opzionale (utile per configurare da smartphone).

**WiFi client:** scan reti, password, profilo salvato in NetworkManager. Con Ethernet attiva puoi aggiungere anche il WiFi (dual-homed).

### Ingressi MIDI

| Sorgente | Stato | Note |
|----------|-------|------|
| **RTP-MIDI (rete)** | ✅ Attivo | Da Mac/PC/iPad verso `tabloza-me` — vedi sezione RTP-MIDI sotto |
| **USB‑MIDI (dongle sul Pi)** | ✅ Attivo | Tastiera/controller via adattatore USB; routing automatico + hot‑plug |
| **GPIO DIN (UART)** | 🔜 Sviluppo futuro | Presa MIDI classica su GPIO 14/15 con optoisolatore; script UART pronto, bridge ALSA da integrare |

In **Stato → Ingressi MIDI** compaiono le sorgenti attive. Dopo aver collegato un dongle USB, attendi ~5 s o usa **MIDI Reset**.

### Motore synth (FluidSynth)

Sezione **Motore synth** (collassabile). Le impostazioni sono salvate in `config.json` e persistono tra reboot.

| Parametro | Descrizione | Riavvio synth |
|-----------|-------------|---------------|
| **Preset buffer audio** | `Standard` (512×6), `Bassa latenza` (256×4), `Stabile` (1024×8) | Sì |
| **Polifonia** | 32–512 voci simultanee (default 256) | No |
| **Riverbero** | Effetto reverb FluidSynth | No |
| **Chorus** | Effetto chorus FluidSynth | No |
| **Caricamento dinamico SF2** | Carica campioni SF2 on demand (meno RAM, più I/O) | Sì |

- **Applica** — salva e applica; riavvia FluidSynth solo se necessario (buffer o caricamento dinamico).
- **Ripristina standard** — torna al preset Standard con polifonia 256, reverb/chorus attivi.
- **Stop note** — invia all-notes-off senza riavviare il motore.

Consigli:
- **Standard** — equilibrio generale su Pi 4/5.
- **Bassa latenza** — live/performance; più carico CPU.
- **Stabile** — SF2 molto grandi o sistemi sotto stress.

### Uscita audio

| Controllo | Descrizione |
|-----------|-------------|
| **Volume uscita audio** | Percentuale 0–100 sul mixer ALSA (PCM/Headphone/Master del dispositivo attivo) |
| **Dispositivo** | Scheda ALSA per FluidSynth: jack `plughw:0,0`, USB `hw:N,0`, HDMI, ecc. |
| **Applica uscita** | Cambia dispositivo e riavvia il synth |
| **Test suono** | Nota di prova via FluidSynth (verifica SF2 + routing) |
| **Test jack** | Beep diretto sull’hardware ALSA (bypass FluidSynth) |

Su schede USB/HDMI il sample rate può passare automaticamente a 48 kHz.

### Diagnostica

Sezione collassabile **Diagnostica** con aggiornamento automatico ogni ~2 s mentre è aperta:

| Blocco | Contenuto |
|--------|-----------|
| **RAM** | Utilizzo percentuale, MB usati/totali, memoria libera, RAM FluidSynth |
| **CPU** | Percentuale utilizzo, load average, numero core |
| **Disco** | Spazio usato/libero su `/var/lib/tabloza`, limite upload SF2 |
| **Temperatura** | SoC Raspberry Pi (thermal zone o `vcgencmd`) |
| **Aggiornamenti** | Pulsante **Verifica aggiornamenti** (GitHub → `sudo tabloza-update`) |
| **Console eventi** | Log testuali (WiFi, rete, SF2, synth, web…) con pulsante **Svuota** |

### Aggiornamenti software

**Dal pannello:** **Diagnostica → Verifica aggiornamenti**. Se disponibile, l’installazione parte in background e i servizi vengono riavviati.

**Da SSH:**

```bash
sudo tabloza-update              # installa ultima versione da GitHub
sudo tabloza-update --check-only # solo controllo (exit 0=ok, 2=disponibile)
```

I dati in `/var/lib/tabloza/` (SF2, password, impostazioni synth) vengono preservati.

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
- **Test jack** verifica l'hardware ALSA direttamente (bypass FluidSynth)
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
sudo systemctl restart tabloza-web tabloza-orchestrator tabloza-wifi tabloza-lan rtpmidid
```

### Disinstallazione e reinstallazione pulita

**Se hai già una versione precedente** e vuoi ripartire da zero:

```bash
# 1. Disinstalla (se il comando esiste)
sudo tabloza-uninstall

# Se tabloza-uninstall non esiste ancora, disinstalla manualmente:
sudo systemctl stop tabloza-web tabloza-orchestrator tabloza-wifi tabloza-lan rtpmidid
sudo systemctl disable tabloza-web tabloza-orchestrator tabloza-wifi tabloza-lan rtpmidid
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
├── config.json      # SF2 attivo, volume (%), fluidsynth (preset, polifonia, effetti…)
├── auth.json        # hash password
├── secret.key       # secret key Flask
└── soundfonts/      # libreria .sf2
```

Esempio sezione `fluidsynth` in `config.json`:

```json
{
  "active_soundfont": "piano.sf2",
  "volume": 85,
  "fluidsynth": {
    "audio_device": "plughw:0,0",
    "audio_preset": "standard",
    "polyphony": 256,
    "reverb": true,
    "chorus": true,
    "dynamic_sample_loading": false
  }
}
```

### Servizi

```bash
sudo systemctl status tabloza-web tabloza-orchestrator tabloza-wifi tabloza-lan rtpmidid
```

| Servizio | Ruolo |
|----------|-------|
| `tabloza-web` | Pannello Flask |
| `tabloza-orchestrator` | FluidSynth, routing MIDI, caricamento SF2 |
| `tabloza-wifi` | Monitor WiFi, hotspot fallback |
| `tabloza-lan` | Monitor Ethernet, link LAN diretto automatico |
| `rtpmidid` | Sessione RTP-MIDI di rete |

### Troubleshooting

Vedi [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### Aggiornamento

```bash
sudo tabloza-update
```

Oppure dal pannello web: **Diagnostica → Verifica aggiornamenti**.

Reinstallazione completa (mantiene i dati se non elimini `/var/lib/tabloza`):

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

---

## Licenza

MIT

# Tabloza MidiExpander

**Italiano** · **[English](README-en.md)**

Trasforma un Raspberry Pi in un expander MIDI headless con sintesi SoundFont, RTP-MIDI e pannello web da smartphone.

Il progetto nasce come supporto al sito [www.tabloza.live](https://www.tabloza.live) per la sua app karaoke **Tabloza Sing**.

---

### Cos'è Tabloza MidiExpander

Tabloza MidiExpander è un **sintetizzatore MIDI standalone** basato su Raspberry Pi. Il dispositivo funziona **senza schermo e senza tasti**: tutto si controlla da browser (smartphone o PC) tramite una interfaccia web responsive.

Riceve note MIDI via **RTP-MIDI di rete** (compatibile con iOS, macOS e Windows) e, in parallelo, da **dongle USB‑MIDI** collegato al Pi. L’audio usa **FluidSynth** e file SoundFont (`.sf2`), con uscita configurabile (jack, USB, HDMI, Bluetooth opzionale).

> **Sviluppi futuri:** ingresso **MIDI GPIO** (porta DIN su UART GPIO 14/15 + optoisolatore) — non ancora implementato. Dettagli in [docs/TODO.md](docs/TODO.md).

### Funzionalità

| Funzione | Descrizione |
|----------|-------------|
| **Sintesi SF2** | FluidSynth con libreria SoundFont gestibile da web; verifica caricamento; **Espelli SF2** libera RAM |
| **Motore synth** | Preset buffer audio (default **Stabile**), polifonia, riverbero, chorus, caricamento dinamico SF2 |
| **Impostazioni MIDI** | Modalità banchi GM/GS/XG/MMA (default GS), buffer anti-jitter RTP, **SysEx auto** hardware-like |
| **Gateway MIDI** | Porta ALSA `Tabloza Buffer`: buffer RTP (~25 ms) + intercettazione SysEx verso FluidSynth |
| **Uscita audio** | Selezione dispositivo (jack, USB, HDMI, Bluetooth ascolto) con volume in percentuale |
| **RTP-MIDI** | Visibile in rete come `tabloza-me.local` (rtpmidid + Avahi) |
| **MIDI USB** | Dongle/interfaccia USB‑MIDI sul Pi, routing automatico in parallelo alla rete |
| **Pannello web** | UI responsive bilingue (IT/EN), sezioni espandibili |
| **Upload SF2** | Drag-and-drop con barra di progresso (max 2 GB); attivazione manuale o automatica |
| **Rete adattiva** | Ethernet, WiFi client, hotspot, link LAN diretto; UI che mostra solo le opzioni pertinenti |
| **Link LAN diretto** | Cavo Pi ↔ computer senza router: DHCP automatico su `192.168.5.1` |
| **WiFi provisioning** | Hotspot `Tabloza-MidiExpander` se non c’è rete; connessione a reti domestiche |
| **Monitor rete** | Riconnessione WiFi, fallback hotspot, gestione automatica Ethernet |
| **Diagnostica** | RAM, CPU, disco, temperatura, console eventi e verifica aggiornamenti |
| **MIDI Reset / Stop note** | Riavvio FluidSynth + routing; silenzia tutte le note senza riavvio |
| **Sicurezza** | Login con password (default: `tabloza`) |

### Interfaccia web (UI)

Accesso: **http://tabloza-me.local** (o l’IP mostrato in Stato)

La UI è **bilingue** (IT/EN): usa i pulsanti **IT** / **EN** in alto. La lingua scelta viene salvata nel browser.

| Sezione | Cosa fa |
|---------|---------|
| **Stato** | Indirizzo mDNS, IP per interfaccia, modalità rete, SF2, versione, **connessioni**, test suono/jack, **MIDI Reset**, **Stop note** |
| **Volume uscita audio** | Slider **0–100%**, salvato automaticamente |
| **Uscita audio** | Elenco dispositivi ALSA + Bluetooth (se accoppiato); cambio uscita con riavvio synth |
| **Motore synth** | Preset buffer audio, polifonia, riverbero, chorus, caricamento dinamico |
| **Impostazioni MIDI** | Modalità banchi, buffer RTP anti-jitter, SysEx automatico; mostra modalità attiva in runtime |
| **Libreria SoundFont** | Lista, carica, elimina, upload `.sf2`, **Espelli SF2** (scarica da RAM) |
| **Rete** | Badge modalità attiva; link LAN diretto, hotspot, WiFi client; **disattiva/attiva WiFi** |
| **Diagnostica** | Metriche sistema (RAM, CPU, disco, temperatura), verifica aggiornamenti, **riavvio dispositivo**, console eventi |
| **Sicurezza** | Cambio password (sezione collassabile) |

### Modalità di rete

Il pannello rileva automaticamente la connettività e adatta i controlli disponibili.

| Modalità (Stato) | Significato |
|------------------|-------------|
| **Ethernet** | Solo cavo LAN al router |
| **WiFi (*nome rete*)** | Solo WiFi client |
| **Ethernet + WiFi (*nome rete*)** | Cavo e WiFi client attivi insieme |
| **Hotspot** | Pi emette `Tabloza-MidiExpander` (password `tabloza-hotspot`) → `http://192.168.4.1` |
| **Link LAN diretto** | Cavo diretto Pi ↔ computer, Pi @ `192.168.5.1` |
| **Offline** | Nessuna connessione utile |

**IP in Stato:** con più interfacce attive vengono mostrati entrambi, es. `192.168.178.143 (Ethernet) · 192.168.178.50 (WiFi)`.

**Ethernet con router:** il Pi tenta prima il DHCP normale. Se il cavo è collegato ma non arriva IP entro ~25 s (es. link diretto a un computer), passa automaticamente al **link LAN diretto** (`192.168.5.1`, DHCP sul cavo). Puoi forzare avvio/stop dal pannello.

**Hotspot:** parte automaticamente se non c’è Ethernet né WiFi raggiungibile; password WPA2 `tabloza-hotspot`, pannello su `http://192.168.4.1`. Se hai già una rete WiFi salvata e in copertura, staccando il cavo il Pi si collega a quella (non apre l’hotspot). Con cavo al router, l’hotspot resta opzionale dal pannello.

**WiFi client:** scan reti, password, profilo salvato in NetworkManager. Con Ethernet attiva puoi aggiungere anche il WiFi (dual-homed). Da **Rete → Disattiva WiFi** spegni la radio (utile con cavo Ethernet o link LAN diretto).

**Router (Ethernet/WiFi) o link LAN diretto?** Quando possibile preferisci collegare il Pi al router (via cavo o WiFi): il pannello resta raggiungibile da qualsiasi dispositivo della rete, non solo dal computer collegato via cavo. Usa il **link LAN diretto** solo quando non hai un router a disposizione (es. in mobilità).

**Forza sempre Link LAN diretto:** in **Rete**, opzione disattivabile di default. Se attivata, qualunque cavo Ethernet collegato passa subito in modalità LAN diretto (`192.168.5.1`), saltando il tentativo di DHCP normale — utile se colleghi sempre il Pi direttamente a un computer (es. per RTP-MIDI via cavo) e vuoi un comportamento prevedibile senza attendere i ~25 s di grace period. **Attenzione:** su una rete con router/switch condivisi con altri dispositivi crea un conflitto (doppio server DHCP sulla stessa rete) — usala solo con un cavo diretto Pi↔computer.

**Link LAN diretto + computer già connesso a internet via WiFi:** il link diretto condivide (NAT) la connessione WiFi del Pi verso il computer via cavo, quindi offre anche lui un gateway di default (necessario per funzionare). Se il computer ha già una propria connessione internet (il suo WiFi), verifica che l'interfaccia WiFi abbia **priorità più alta** del cavo Ethernet — altrimenti il traffico generale del computer rischia di passare per il doppio salto computer→Pi→WiFi del Pi invece che direttamente, con internet lento o non funzionante:

- **macOS:** Impostazioni di Sistema → Rete → menu **···** → *Imposta ordine dei servizi* → trascina **Wi-Fi** sopra la scheda Ethernet/USB LAN. Da terminale: `sudo networksetup -ordernetworkservices Wi-Fi "USB 10/100 LAN"` (aggiungi gli altri servizi elencati da `networksetup -listnetworkserviceorder`, nello stesso ordine, dopo i primi due).
- **Windows:** Pannello di controllo → Rete e Internet → Centro connessioni di rete → *Modifica impostazioni scheda* → premi **Alt** per mostrare il menu → *Impostazioni avanzate…* → nell'elenco **Connessioni** sposta il Wi-Fi sopra la scheda Ethernet con le frecce su/giù.
- **Linux (NetworkManager):** imposta una metrica di route più bassa (= priorità più alta) sul WiFi rispetto all'Ethernet: `nmcli connection modify <profilo-wifi> ipv4.route-metric 50` e `nmcli connection modify <profilo-ethernet> ipv4.route-metric 100`.

### Connessioni (MIDI + synth)

| Sorgente | Stato | Note |
|----------|-------|------|
| **RTP-MIDI (rete)** | ✅ Attivo | Da Mac/PC/iPad verso `tabloza-me` — vedi sezione RTP-MIDI sotto |
| **USB‑MIDI (dongle sul Pi)** | ✅ Attivo | Tastiera/controller via adattatore USB; routing automatico + hot‑plug |
| **GPIO DIN (UART)** | 🔜 Sviluppo futuro | Presa MIDI classica su GPIO 14/15 con optoisolatore; script UART pronto, bridge ALSA da integrare |

In **Stato → Connessioni** compaiono le sorgenti attive (rtpmidid, USB, Tabloza Sing WSS) e lo stato del synth (FluidSynth). Dopo aver collegato un dongle USB, attendi ~5 s o usa **MIDI Reset**.

#### Percorso MIDI (rete e USB)

Le sorgenti non vanno più direttamente a FluidSynth: passano dal **gateway Tabloza** (porta ALSA `Tabloza Buffer`), che può:

1. **Buffer RTP** (opzionale, ~25 ms) — smussa jitter WiFi prima del synth  
2. **SysEx auto** (opzionale) — rileva SysEx GM/GS/XG/GM2 e cambia la modalità banchi in tempo reale  

```
Mac/iPad/USB  →  rtpmidid / USB-MIDI  →  Tabloza Buffer  →  FluidSynth
```

Con buffer RTP disattivato ma SysEx auto attivo, il gateway resta acceso in **passthrough** (latenza MIDI minima, intercettazione SysEx attiva).

### Impostazioni MIDI

Sezione **Impostazioni MIDI** (collassabile). Salvate in `config.json` → sezione `midi`.

| Parametro | Descrizione | Riavvio synth |
|-----------|-------------|---------------|
| **Modalità banchi** | `GM`, `GS` (default), `XG`, `MMA/GM2` — come FluidSynth interpreta i bank select | Sì |
| **Buffer anti-jitter RTP** | Ritarda eventi di rete ~25 ms (default **attivo**); utile su WiFi | No (solo gateway) |
| **Timestamp RTP (rtpmidid-ts)** | Schedula ALSA dall'orologio RTP del mittente (default **attivo**) | Riavvia rtpmidid |
| **SysEx automatico** | Cambia modalità banchi al volo su SysEx GM/GS/XG/GM2 (default **attivo**) | No |

**Quando usare quale modalità banchi:**

| Modalità | Consigliata per |
|----------|-----------------|
| **GM** | App semplici, file MIDI GM puri (ignora bank select) |
| **GS** | Compromesso generico, SF2 GM/GS, strumenti Roland |
| **XG** | SoundFont Yamaha (es. SD1000), file/arranger XG |
| **MMA** | File GM2 o DAW con MSB+LSB espliciti |

Con **SysEx automatico** attivo, un file o una app che manda ad es. *XG System On* passa temporaneamente in modalità XG (visibile come «modalità attiva ora» nel pannello), senza modificare il default salvato. GM2 via SysEx viene mappato a **MMA**.

Altri SysEx (tuning, GS DT1 ritmici, ecc.) vengono inoltrati normalmente a FluidSynth.

### Motore synth (FluidSynth)

Sezione **Motore synth** (collassabile). Le impostazioni sono salvate in `config.json` e persistono tra reboot.

| Parametro | Descrizione | Riavvio synth |
|-----------|-------------|---------------|
| **Preset buffer audio** | `Standard` (512×6), `Bassa latenza` (256×4), `Stabile` (1024×8) — **default: Stabile** | Sì |
| **Polifonia** | 32–512 voci simultanee (default 256) | Sì |
| **Riverbero** | Effetto reverb FluidSynth | No |
| **Chorus** | Effetto chorus FluidSynth | No |
| **Caricamento dinamico SF2** | Carica campioni SF2 on demand (meno RAM, più I/O) | Sì |

- **Applica** — salva e applica; riavvia FluidSynth solo se necessario (buffer audio o caricamento dinamico).
- **Ripristina stabile** — torna al preset **Stabile** (1024×8) con polifonia 256, reverb/chorus attivi.

Consigli:
- **Stabile** (default) — SF2 grandi (es. SD1000), WiFi/RTP, sistemi sotto stress; ~185 ms latenza audio.
- **Standard** — equilibrio generale su Pi 4/5 (~70 ms latenza audio).
- **Bassa latenza** — live/performance; più carico CPU (~40 ms latenza audio).

> Il **buffer RTP MIDI** (~25 ms) è separato dal buffer audio e si configura in **Impostazioni MIDI**.

### Libreria SoundFont

Oltre a selezionare e caricare `.sf2` via upload:

- **Carica** — carica lo SF2 selezionato in FluidSynth (con verifica nello stack synth e timeout adattivo per file grandi).
- **Espelli SF2** — scarica tutti gli SF2 da RAM lasciando FluidSynth attivo (utile con mappe da 1+ GB).
- Prima di ogni nuovo caricamento, eventuali SF2 precedenti vengono scaricati automaticamente.
- I nomi file con **spazi** sono supportati (es. `SD1000 Sound Family Map.sf2`).

### Uscita audio

| Controllo | Descrizione |
|-----------|-------------|
| **Volume uscita audio** | 0–100% sul mixer ALSA (jack/USB/HDMI) o sul sink Pulse (Bluetooth) |
| **Dispositivo** | Jack `plughw:0,0`, USB, HDMI, oppure **Bluetooth — …** (ascolto opzionale via A2DP) |
| **Applica uscita** | Cambia dispositivo e riavvia il synth |
| **Test suono** | Nota di prova via FluidSynth (verifica SF2 + routing) |
| **Test jack** | Beep diretto sull’hardware ALSA; su Bluetooth invia invece una nota MIDI |
| **Stop note** | Silenzia tutte le note (in **Stato**, accanto a MIDI Reset) |

Su schede USB/HDMI il sample rate può passare automaticamente a 48 kHz.

**Bluetooth (ascolto opzionale):** nel pannello, sezione **Bluetooth (ascolto)** — scansione e accoppiamento guidato (utile su Pi OS Lite senza GUI). Poi seleziona `Bluetooth — …` come uscita. Latenza tipicamente più alta rispetto a jack/USB.

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

1. Connettiti alla rete del dispositivo o all'hotspot `Tabloza-MidiExpander` (password WiFi: `tabloza-hotspot`)
2. Apri **http://tabloza-me.local** (o `http://192.168.4.1` se sei sull’hotspot, o `http://<IP-del-Pi>`)
3. Password pannello web: `tabloza`

### Configurazione RTP-MIDI wireless

Il Pi annuncia **una sola** sessione RTP-MIDI sulla rete:
- **Nome:** `tabloza-me`
- **Porta UDP:** `5004`
- **mDNS:** `tabloza-me.local`

> **Annuncio unico e doppia interfaccia (Ethernet + WiFi)**  
> In Configurazione MIDI del Mac compare **un solo** nome `tabloza-me`, anche se il Pi ha cavo e WiFi attivi insieme. mDNS non distingue «WiFi» da «Ethernet» nel nome: serve a **scoprire** il dispositivo, non a indicare quale cavo usa la sessione attiva.  
> La sessione RTP-MIDI usa **un solo percorso IP** (es. IP WiFi *oppure* IP Ethernet). Se ti connetti via WiFi e poi spegni il WiFi sul Pi, il MIDI **si interrompe** anche se il cavo Ethernet è ancora collegato — devi **riconnetterti**, preferibilmente con **connessione manuale** all’IP giusto (vedi sotto).  
> In **Stato** vedi gli IP per interfaccia, es. `192.168.5.1 (Ethernet) · 192.168.178.50 (WiFi)`. Per lavorare solo col cavo diretto: disattiva il WiFi dal pannello (**Rete → Disattiva WiFi**) e connetti manualmente a `192.168.5.1` porta **5004**.

Prerequisiti sul Pi: carica un file `.sf2` dal pannello web e verifica con `sudo tabloza-test`.

#### macOS / iOS

1. Mac e Pi sulla **stessa rete WiFi/LAN**
2. Apri **Configurazione Audio e MIDI** → **Finestra → Mostra Studio MIDI**
3. **macOS Sequoia / Tahoe (15+):** **Finestra → Configura driver di rete** (non più doppio clic su Rete)
   - **macOS più vecchi:** doppio clic sull'icona **Rete** (globo)
4. Crea una sessione **RTP** (pulsante **+** in «Le mie sessioni») e attiva la spunta
5. In **Directory** cerca **`tabloza-me`** → **Connetti**
6. Se non compare: **Connetti manualmente** con host = **IP del Pi** (quello giusto per la rete che usi, vedi Stato) porta **5004** — non usare `tabloza-me.local` se risolve all’IP sbagliato con due interfacce attive
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

# 3. FluidSynth, gateway MIDI e routing
pgrep -a fluidsynth
aconnect -l | grep -E 'Tabloza|fluidsynth|rtpmidid|Connected'

# 4. Nota di test diretta (senza Mac)
FS=$(aconnect -i | grep -i fluidsynth | head -1 | awk '{print $2}')
sudo amidi -p "$FS" -S "90 3C 64" && sleep 0.3 && sudo amidi -p "$FS" -S "80 3C 00"

# 5. Log in tempo reale mentre suoni dal Mac
sudo journalctl -u tabloza-orchestrator -f
```

**Interpretazione:**
| Test suono (web) | MIDI in (web) | Probabile causa |
|------------------|---------------|-----------------|
| Si sente | No lampeggia | Mac non invia MIDI o routing RTP → gateway/FluidSynth rotto → **MIDI Reset** |
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
├── config.json      # SF2 attivo, volume (%), fluidsynth, midi (banchi, buffer RTP, SysEx)…
├── auth.json        # hash password
├── secret.key       # secret key Flask
└── soundfonts/      # libreria .sf2
```

Esempio `config.json` (estratti):

```json
{
  "active_soundfont": "piano.sf2",
  "volume": 85,
  "fluidsynth": {
    "audio_device": "plughw:0,0",
    "audio_preset": "stable",
    "period_size": 1024,
    "period_count": 8,
    "polyphony": 256,
    "reverb": true,
    "chorus": true,
    "dynamic_sample_loading": false
  },
  "midi": {
    "bank_select": "gs",
    "jitter_buffer_enabled": true,
    "jitter_buffer_ms": 25,
    "rtp_midi_timestamps_enabled": true,
    "sysex_bank_auto": true
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
| `tabloza-orchestrator` | FluidSynth, gateway MIDI (`Tabloza Buffer`), routing, caricamento SF2, SysEx auto |
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

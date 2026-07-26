# Troubleshooting — Tabloza MidiExpander

## Accesso web

### rtpmidid non si installa / `Unable to locate package rtpmidid`

Normale su Raspberry Pi OS: `rtpmidid` **non è nei repository apt**. L'installer scarica [rtpmidid-ts](https://github.com/mccoy88f/rtpmidid-ts) (fork Tabloza con timestamp RTP) o lo compila da sorgente.

Riesegui l'installazione aggiornata:

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

### Non raggiungo tabloza-me.local né l'IP

1. Verifica che il servizio web sia attivo:
   ```bash
   sudo systemctl status tabloza-web
   sudo ss -tlnp | grep ':80 '
   ```
2. Prova l'**IP diretto** (senza `.local`):
   ```bash
   hostname -I    # sul Pi
   ```
   Poi dal browser: `http://192.168.x.x` (sostituisci con il tuo IP)
3. Se hai una versione vecchia, prova anche `http://<IP>:8080` (porta precedente)
4. Stessa rete LAN/WiFi del Pi (o connesso all'hotspot `Tabloza-MidiExpander`)
5. Verifica Avahi: `systemctl status avahi-daemon`
6. Su Windows potrebbe servire [Bonjour](https://support.apple.com/kb/DL999) per `.local`
7. Riavvia i servizi:
   ```bash
   sudo systemctl restart tabloza-web avahi-daemon
   ```

### Non raggiungo solo tabloza-me.local (ma l'IP funziona)

1. Verifica che il dispositivo sia acceso e connesso alla stessa rete del telefono
2. In modalità hotspot, connettiti a `Tabloza-MidiExpander` e apri `http://192.168.4.1`
3. Prova l'IP diretto mostrato nel terminale: `hostname -I`
4. Verifica Avahi: `systemctl status avahi-daemon`
5. Su Windows potrebbe servire [Bonjour](https://support.apple.com/kb/DL999) per `.local`

### Il pannello funziona con l'IP ma non con tabloza-me.local (errore 301 / pagina vuota)

Succede se il browser ha memorizzato **HTTPS** per `tabloza-me.local` (versioni v2.3.x del pannello). L'IP non ha quella cache, quindi funziona.

**Fix automatico (v2.5.5+):** il Pi risponde su `https://tabloza-me.local` con redirect a `http://`. Aggiorna:

```bash
sudo tabloza-update
sudo systemctl restart tabloza-web
```

**Fix manuale nel browser:**

1. Apri sempre l'URL completo: `http://tabloza-me.local` (non `https://`)
2. **Chrome:** `chrome://net-internals/#hsts` → *Delete domain security policies* → `tabloza-me.local`
3. **Chrome:** Impostazioni → Privacy → Sicurezza → disattiva temporaneamente *Usa sempre connessioni sicure*
4. **Safari:** Sviluppo → Svuota cache; se persiste, cancella dati sito per `tabloza-me.local`
5. In DevTools → Network, verifica che `/api/status` risponda `401` o `200`, non `301` verso `https://`
6. Se vedi **301 (disk cache)** su `status`, aggiorna a v2.5.6+ (`sudo tabloza-update`) oppure svuota la cache del sito per `tabloza-me.local`

Verifica dal Mac/PC:

```bash
curl -sI http://tabloza-me.local/api/status    # atteso: 401
curl -skI https://tabloza-me.local/api/status # v2.5.5+: Location: http://...
```

### Password non accettata

- Password predefinita: `tabloza`
- Reset manuale:
  ```bash
  sudo python3 -c "import bcrypt; print(bcrypt.hashpw(b'tabloza', bcrypt.gensalt()).decode())"
  # Copia l'hash in /var/lib/tabloza/auth.json
  ```

---

## RTP-MIDI

### Il Mac mostra tabloza-me, tabloza-me #1 e/o FluidSynth

Cause tipiche (versioni precedenti a v1.3.22):

1. **Doppio annuncio RTP-MIDI** — Avahi statico + rtpmidid (stesso nome → `#1` su macOS)
2. **`alsa_announce` in rtpmidid** — espone FluidSynth come endpoint di rete separato

**Fix sul Pi:**
```bash
sudo tabloza-update
sudo bash /opt/tabloza/scripts/configure-rtpmidid.sh /opt/tabloza/config/rtpmidid/default.ini
sudo bash /opt/tabloza/scripts/configure-avahi.sh /opt/tabloza
sudo systemctl restart rtpmidid avahi-daemon
```

Sul Mac, in **Studio MIDI → Rete**, elimina sessioni vecchie verso il Pi e riconnetti solo a **`tabloza-me`**.

Verifica (Pi): `avahi-browse -r _apple-midi._udp | grep -i tabloza` — deve comparire **una sola** sessione `tabloza-me` (niente Fluid Synth in rete).

### Il Mac non vede tabloza-me in Audio MIDI Setup (ma il web funziona)

Il web (`http://tabloza-me.local`) e il MIDI wireless usano **servizi mDNS diversi**:
- Web → `_http._tcp`
- MIDI → `_apple-midi._udp` porta **5004**

**Sul Mac** (Terminale), verifica se il MIDI è annunciato:
```bash
dns-sd -B _apple-midi._udp local.
```
Attendi 10 secondi. Se non compare `tabloza-me`, il problema è sul Pi.

**Sul Pi** (SSH):
```bash
sudo bash /opt/tabloza/scripts/configure-rtpmidid.sh
sudo bash /opt/tabloza/scripts/configure-avahi.sh /opt/tabloza
sudo systemctl restart rtpmidid avahi-daemon tabloza-orchestrator
sudo ss -ulnp | grep 5004
sudo tabloza-test
```

**Su Mac — Configurazione Audio e MIDI:**
1. Finestra → Mostra Studio MIDI → doppio clic **Rete**
2. In **Le mie sessioni**: clic **+**, inserisci un nome, **attiva la spunta**
3. In **Directory** cerca **`tabloza-me`** → **Connetti** (una sola voce; elimina sessioni vecchie se vedi duplicati)
4. Se non compare: attendi 30s e riprova dopo i comandi sul Pi sopra

### Il Mac/iPad non vede il dispositivo

1. `systemctl status rtpmidid` — deve essere attivo
2. `systemctl status avahi-daemon` — mDNS attivo
3. Hostname: `tabloza-me.local`
4. Riavvia: `sudo systemctl restart rtpmidid avahi-daemon`

### MIDI di rete non produce suono

1. Nel pannello web, premi **MIDI Reset** (sezione Stato) per riavviare rtpmidid e FluidSynth
2. Verifica routing: `aconnect -o` e `aconnect -i`
2. Cerca porte `rtpmidid` e `Fluid Synth`
3. Riavvia orchestratore: `sudo systemctl restart tabloza-orchestrator`
4. Log: `journalctl -u tabloza-orchestrator -f`

### `fluidsynth.log` mostra "SysEx DT1: dropping message ... incorrect checksum"

Alcuni file MIDI GS incorporano SysEx di sistema (es. Reverb/Chorus Macro,
indirizzo `0x40 0x01 0x00`) con un byte di checksum scorretto già nel file
sorgente — non generato da Tabloza. FluidSynth lo scarta correttamente
perché il checksum non torna; l'effetto è solo un preset di reverb/chorus
non applicato, non riguarda il timing delle note.

**Fix (v2.5.29+):** `repair_gs_sysex_checksum()` in `src/midi_sysex_mode.py`
ricalcola il checksum Roland GS (somma indirizzo+dati, 128 - somma mod 128)
prima di inoltrare il messaggio a FluidSynth, così i SysEx GS con checksum
errato nel file sorgente vengono corretti invece di scartati. Il gateway
MIDI (`src/midi_jitter_buffer.py`, `_forward_message`) applica la
correzione automaticamente su ogni SysEx in transito.

---

## Audio

### Nessun suono dall'uscita jack

1. Volume nel pannello web > 0
2. Un SoundFont caricato e attivo
3. Test ALSA: `speaker-test -t wav -c 2` (Ctrl+C per uscire)
4. FluidSynth attivo: `systemctl status tabloza-orchestrator`
5. Log FluidSynth: `journalctl -u tabloza-orchestrator -n 50`

### Bluetooth non compare / nessun suono

1. Nel pannello: **Uscita audio → Bluetooth → 1. Avvia scansione** (cuffie in pairing), poi **2. Accoppia e collega**
2. Seleziona `Bluetooth — …` nell’elenco uscite → **Applica uscita**
3. Verifica sink: `pactl list short sinks | grep -i bluez`
4. Se manca `pactl`/`bluetoothctl`: `sudo apt install pipewire-pulse pulseaudio-utils bluez` poi `sudo tabloza-update`
5. Latenza elevata è normale su A2DP — per live usa jack/USB/HDMI

**`br-connection-profile-unavailable`:** manca il profilo A2DP sul Pi (WirePlumber non ha registrato Audio Source). Su Lite headless è tipico senza fix seat-monitoring (v2.5.14+). Verifica:

```bash
bluetoothctl show | grep -i "Audio Source"
# deve comparire UUID Audio Source (0000110a-…)
wpctl status   # deve elencare Devices bluez5 dopo connect
```

Se manca Audio Source: `sudo tabloza-update` (installa `/etc/wireplumber/.../51-disable-bluez-seat-monitoring.conf`) oppure riavvia `systemctl --user restart wireplumber` come utente `pi`.

**`br-connection-refused`:** cuffie già collegate al telefono, spente o non in ascolto — disconnettile dal telefono, riapri la custodia e riprova Accoppia/Collega.

Alternativa da SSH (senza pannello):

```bash
bluetoothctl
power on
scan on
# … pair / trust / connect …
```

### Audio scattante

- Usa Pi 4 o 5 (Pi 3 ha limitazioni)
- In `/var/lib/tabloza/config.json` aumenta `period_size` (es. 512) e `period_count` (es. 4)
- Riavvia: `sudo systemctl restart tabloza-orchestrator`

---

## WiFi

### Hotspot non si attiva

1. `systemctl status tabloza-wifi tabloza-lan`
2. Log: `journalctl -u tabloza-wifi -u tabloza-lan -n 50 --no-pager`
3. Verifica radio: `nmcli radio` (deve essere `WIFI: enabled`)
4. Verifica profilo: `nmcli connection show tabloza-hotspot`
5. Avvio manuale: `sudo nmcli connection up tabloza-hotspot`
6. Riavvia: `sudo systemctl restart NetworkManager tabloza-wifi tabloza-lan`

**Note (v2.5.8+):**
- SSID: `Tabloza-MidiExpander` — password WPA2: **`tabloza-hotspot`** → pannello `http://192.168.4.1`
- Se hai già una rete WiFi salvata e in copertura, staccando il cavo LAN il Pi **si collega a quella rete** (non apre l’hotspot)
- Se dal pannello hai premuto **Disattiva WiFi**, la radio resta spenta: riattivala o aggiorna a v2.5.8+ (il fallback la riaccende da solo)

### WiFi si disconnette

Il servizio `tabloza-wifi` monitora ogni 30 secondi e tenta riconnessione o hotspot automatico.

### Hotspot attivo (mi connetto alla rete) ma né l'IP né tabloza-me.local aprono il pannello

Causa tipica: manca `dnsmasq-base` sul Pi. NetworkManager (`ipv4.method=shared`,
usato dal profilo `tabloza-hotspot`) delega a `dnsmasq` il DHCP/DNS per i client
dell'AP. Senza quel binario l'hotspot si accende comunque (SSID visibile,
associazione WiFi riuscita) ma **nessun client riceve un IP valido** sulla
subnet `192.168.4.0/24` — il telefono resta con un IP a vuoto o auto-assegnato
(`169.254.x.x`), quindi non ha una rotta né verso `192.168.4.1` né verso il
nome mDNS risolto.

**Verifica sul Pi** (con hotspot attivo):
```bash
which dnsmasq || echo "dnsmasq NON installato"
journalctl -u NetworkManager -n 100 --no-pager | grep -i dnsmasq
ip -4 addr show wlan0   # atteso: 192.168.4.1/24
```
Sul telefono, controlla l'IP assegnato nei dettagli della rete `Tabloza-MidiExpander`:
se è `169.254.x.x` o assente, conferma il problema.

**Fix (v2.5.25+):** `sudo tabloza-update` installa `dnsmasq-base` e maschera un
eventuale `dnsmasq.service` di sistema (che altrimenti confligge sulle porte
53/67 con l'istanza lanciata da NetworkManager per l'hotspot). Poi:
```bash
sudo nmcli connection down tabloza-hotspot 2>/dev/null || true
sudo systemctl restart tabloza-wifi
```

### Link LAN diretto attivo: il computer perde/non ha più internet

Il **link LAN diretto** (`ipv4.method=shared`, vedi README § Modalità di rete)
condivide via NAT la connessione WiFi del Pi verso il computer collegato via
cavo — per funzionare offre quindi anche lui, via DHCP sul cavo, un gateway
di default. Se il computer ha già una propria connessione internet (il suo
WiFi), può capitare che il sistema operativo preferisca instradare tutto il
traffico attraverso il cavo (doppio salto computer→Pi→WiFi del Pi) invece che
direttamente dal proprio WiFi — con internet lento o non funzionante, anche
se il WiFi del computer da solo va benissimo.

**Non è un difetto da disattivare lato Tabloza** (il gateway sul cavo serve
proprio per condividere internet quando il computer non ne ha altro). Il fix
è verificare la priorità delle interfacce di rete **sul computer**, dando
priorità al WiFi rispetto al cavo Ethernet/USB LAN — vedi README §
*Router (Ethernet/WiFi) o link LAN diretto?* per le istruzioni su
macOS/Windows/Linux.

### Note MIDI che arrivano in ritardo "a raffica" (Tabloza Sing via WebSocket)

Causa tipica: **power-save del driver WiFi** (`brcmfmac`, chip BCM4345/6 dei
Raspberry Pi). Con il risparmio energetico attivo la radio dorme tra un beacon
e l'altro; i pacchetti WebSocket in arrivo vengono bufferizzati dal router e
consegnati tutti insieme al risveglio — il jitter buffer software (25 ms sul
gateway "Tabloza Sing WS") assorbe la variazione di rete minima ma non i picchi
di 100-200 ms del power-save, quindi le note si accumulano ed escono a raffica.

**Verifica sul Pi:**
```bash
journalctl -k -b --no-pager | grep -i power_mgmt
# "power save enabled" conferma la causa
```

**Fix (v2.5.26+):** ogni connessione WiFi client creata dal pannello disabilita
il power-save (`802-11-wireless.powersave=2`, vedi `_apply_autoconnect` in
`src/wifi_utils.py`). Per un device già configurato con una versione precedente:
```bash
sudo nmcli connection modify "<nome-connessione-wifi>" 802-11-wireless.powersave 2
sudo nmcli connection up "<nome-connessione-wifi>"
```

**Doppio profilo WiFi per la stessa rete (v2.5.28+):** su un device appena
flashato può esistere già un profilo WiFi creato dall'immagine base (es.
`netplan-wlan0-<ssid>`, da Raspberry Pi Imager/raspi-config) *oltre* a quello
gestito da Tabloza (`tabloza-wifi-<ssid>`). Se al boot NetworkManager si
connette prima al profilo residuo, per qualche secondo il power-save è di
nuovo attivo (il profilo residuo non ha il fix v2.5.26) prima che Tabloza
forzi lo switch al proprio profilo a priorità più alta.

**Fix (v2.5.28+):** `tabloza_claim_wifi_profile()` in `scripts/network-common.sh`
rinomina il profilo WiFi client attivo in `tabloza-wifi-<ssid>` (senza
disconnettere) applicando `powersave=2`, e rimuove ogni altro profilo residuo
per la stessa SSID. Viene chiamata da `wifi-fallback.sh` dopo ogni connessione
riuscita e ad ogni ciclo di `wifi-monitor.sh` (ogni 30s) come rete di
sicurezza, così resta sempre un solo profilo — quello di Tabloza.

---

## Aggiornamento

### Dopo `sudo tabloza-update` il pannello web non torna raggiungibile

`install.sh` ferma `tabloza-web`, `tabloza-orchestrator` e `tabloza-midi-ws`
insieme prima di reinstallare le dipendenze, poi li riavvia tutti insieme a
fine script. Se `tabloza-midi-ws` impiega più tempo a fermarsi (chiusura
delle connessioni WebSocket attive), il successivo `systemctl restart` su più
unit contemporaneamente a volte non fa ripartire `tabloza-web` insieme alle
altre.

**Verifica:**
```bash
systemctl is-active tabloza-web tabloza-orchestrator tabloza-midi-ws
journalctl -u tabloza-web --no-pager | grep -E 'Started|Stopped|Stopping'
```
Se `tabloza-web` risulta `inactive` mentre gli altri sono `active`:
```bash
sudo systemctl start tabloza-web
```

**Fix (v2.5.29+):** a fine `install.sh`, dopo il riavvio di tutti i servizi,
uno script verifica esplicitamente `tabloza-web` e lo riavvia (fino a 10
tentativi, 2s di intervallo) se non risulta attivo — l'aggiornamento non si
considera concluso finché il pannello non è di nuovo su.

---

## Servizi utili

```bash
# Stato di tutti i servizi
sudo systemctl status tabloza-web tabloza-orchestrator tabloza-wifi rtpmidid

# Riavvio completo
sudo systemctl restart rtpmidid tabloza-orchestrator tabloza-web tabloza-wifi

# Reinstallazione
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

## Log

```bash
journalctl -u tabloza-web -f
journalctl -u tabloza-orchestrator -f
journalctl -u tabloza-wifi -f
journalctl -u rtpmidid -f
```

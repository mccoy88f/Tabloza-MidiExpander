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

---

## Audio

### Nessun suono dall'uscita jack

1. Volume nel pannello web > 0
2. Un SoundFont caricato e attivo
3. Test ALSA: `speaker-test -t wav -c 2` (Ctrl+C per uscire)
4. FluidSynth attivo: `systemctl status tabloza-orchestrator`
5. Log FluidSynth: `journalctl -u tabloza-orchestrator -n 50`

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

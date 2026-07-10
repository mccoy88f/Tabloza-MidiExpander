# Troubleshooting — Tabloza MidiExpander

## Accesso web

### rtpmidid non si installa / `Unable to locate package rtpmidid`

Normale su Raspberry Pi OS: `rtpmidid` **non è nei repository apt**. L'installer recente lo scarica automaticamente da [GitHub (davidmoreno/rtpmidid)](https://github.com/davidmoreno/rtpmidid/releases).

Riesegui l'installazione aggiornata:

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

### Non raggiungo tabloza-me.local

1. Verifica che il dispositivo sia acceso e connesso alla stessa rete del telefono
2. In modalità hotspot, connettiti a `Tabloza-MidiExpander` e apri `http://192.168.4.1`
3. Prova l'IP diretto mostrato nel terminale: `hostname -I`
4. Verifica Avahi: `systemctl status avahi-daemon`
5. Su Windows potrebbe servire [Bonjour](https://support.apple.com/kb/DL999) per `.local`

### Password non accettata

- Password predefinita: `tabloza`
- Reset manuale:
  ```bash
  sudo python3 -c "import bcrypt; print(bcrypt.hashpw(b'tabloza', bcrypt.gensalt()).decode())"
  # Copia l'hash in /var/lib/tabloza/auth.json
  ```

---

## RTP-MIDI

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

1. `systemctl status tabloza-wifi`
2. Log: `journalctl -u tabloza-wifi -f`
3. Verifica profilo: `nmcli connection show tabloza-hotspot`
4. Riavvia NetworkManager: `sudo systemctl restart NetworkManager tabloza-wifi`

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

# Tabloza MidiExpander

Trasforma un Raspberry Pi in un **expander MIDI headless** con sintesi SoundFont (SF2), ingresso MIDI fisico, RTP-MIDI di rete e pannello di controllo web da smartphone.

## Requisiti

- **Raspberry Pi 4 o 5** (consigliato) — Pi 3 supportato con prestazioni limitate
- **Raspberry Pi OS Lite 64-bit** già installato sulla SD card
- Accesso terminale (SSH o monitor + tastiera)
- Circuito MIDI IN con optoisolatore su GPIO 14/15 (opzionale per RTP-MIDI solo)

## Installazione

Dopo aver installato Raspberry Pi OS Lite 64-bit e aver effettuato l'accesso al terminale, esegui **una sola riga**:

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

Al termine, riavvia:

```bash
sudo reboot
```

### Cosa fa lo script

1. Installa FluidSynth, rtpmidid, Avahi, NetworkManager e dipendenze Python
2. Configura UART MIDI a 31250 bps su GPIO 14/15
3. Imposta hostname `tabloza-midi` con mDNS (`tabloza-midi.local`)
4. Configura fallback WiFi hotspot (`Tabloza-MidiExpander` @ `192.168.4.1`)
5. Installa e avvia i servizi systemd
6. Crea la directory dati persistente in `/var/lib/tabloza/`

## Primo accesso

1. Connettiti alla rete WiFi del dispositivo **oppure** alla tua rete locale
2. Apri il browser su: **http://tabloza-midi.local** (o `http://192.168.4.1` in modalità hotspot)
3. Accedi con le credenziali predefinite:

| Campo | Valore |
|-------|--------|
| Password | `tabloza` |

> Cambia la password subito da **Impostazioni → Sicurezza** nel pannello web.

## Funzionalità

- Sintesi SF2 in tempo reale (FluidSynth)
- Ingresso MIDI fisico via GPIO UART
- RTP-MIDI di rete (rtpmidid) — visibile da iOS, macOS, Windows
- Upload e gestione libreria SoundFont
- Controllo volume master
- Provisioning WiFi da smartphone (hotspot → rete domestica)

## Struttura dati persistenti

```
/var/lib/tabloza/
├── config.json      # SoundFont attivo, volume
├── auth.json        # hash password
└── soundfonts/      # libreria .sf2
```

## Servizi

```bash
sudo systemctl status tabloza-web
sudo systemctl status tabloza-orchestrator
sudo systemctl status tabloza-wifi
sudo systemctl status rtpmidid
```

## Aggiornamento

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

I dati in `/var/lib/tabloza/` vengono preservati.

## Licenza

MIT

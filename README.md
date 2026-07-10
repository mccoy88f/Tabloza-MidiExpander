# Tabloza MidiExpander

Trasforma un Raspberry Pi in un **expander MIDI headless** con sintesi SoundFont (SF2), RTP-MIDI di rete e pannello di controllo web da smartphone.

## Requisiti

- **Raspberry Pi 4 o 5** (consigliato) — Pi 3 supportato con prestazioni limitate
- **Raspberry Pi OS Lite 64-bit** già installato sulla SD card
- Accesso terminale (SSH o monitor + tastiera)

## Installazione

Dopo aver installato Raspberry Pi OS Lite 64-bit e aver effettuato l'accesso al terminale, esegui **una sola riga**:

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
sudo reboot
```

### Cosa fa lo script

1. Installa FluidSynth, rtpmidid, Avahi, NetworkManager e dipendenze Python
2. Imposta hostname `tabloza-md` con mDNS (**tabloza-md.local**)
3. Configura fallback WiFi hotspot (`Tabloza-MidiExpander` @ `192.168.4.1`)
4. Installa e avvia i servizi systemd
5. Crea la directory dati persistente in `/var/lib/tabloza/`
6. Genera secret key Flask univoca

> **MIDI GPIO fisico:** funzione pianificata, non ancora attiva. Vedi [docs/TODO.md](docs/TODO.md).

## Primo accesso

1. Connettiti alla rete WiFi del dispositivo **oppure** alla tua rete locale
2. Apri il browser su: **http://tabloza-md.local** (o `http://192.168.4.1` in modalità hotspot)
3. Accedi con password predefinita: `tabloza`

> Cambia la password da **Sicurezza** nel pannello web.

## Funzionalità

- Sintesi SF2 in tempo reale (FluidSynth)
- RTP-MIDI di rete (rtpmidid) — visibile come `tabloza-md.local`
- Upload e gestione libreria SoundFont (auto-attivazione dopo upload)
- Controllo volume master (persistente tra reboot)
- Provisioning WiFi da smartphone (hotspot → rete domestica)
- Monitor WiFi con riconnessione automatica
- MIDI GPIO fisico — **in arrivo**

## Struttura dati persistenti

```
/var/lib/tabloza/
├── config.json      # SoundFont attivo, volume
├── auth.json        # hash password
├── secret.key       # secret key Flask (generata all'install)
└── soundfonts/      # libreria .sf2
```

## Servizi

```bash
sudo systemctl status tabloza-web
sudo systemctl status tabloza-orchestrator
sudo systemctl status tabloza-wifi
sudo systemctl status rtpmidid
```

## Troubleshooting

Vedi [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Aggiornamento

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

I dati in `/var/lib/tabloza/` vengono preservati.

## Licenza

MIT

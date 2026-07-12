# Funzionalità pianificate

## MIDI USB (dongle)

**Stato:** attivo — routing automatico in parallelo a RTP-MIDI di rete

- Dongle USB‑MIDI o interfaccia USB collegata al Pi
- L'orchestrator esegue `aconnect` periodico verso FluidSynth (come per `rtpmidid`)
- Visibile in pannello → Stato → **Ingressi MIDI** con badge **Attivo** / **Collegato**
- Hot‑plug: inserire il dongle e attendere ~5 s, oppure **MIDI Reset**

## Tabloza Sing (WebSocket / JZZ-midi-WS)

**Stato:** attivo — ingresso dedicato con buffer anti-jitter separato

- Server `tabloza-midi-ws` su porta **8765** (protocollo JZZ-midi-WS)
- Porta ALSA sorgente `Tabloza Sing` → gateway `Tabloza Sing WS` (buffer ~25 ms) → FluidSynth
- Configurazione: `config.json` → `midi.ws_jitter_buffer_ms` / `ws_jitter_buffer_enabled`
- In Tabloza Sing: banco sonoro **Tabloza MidiExpander** (`midi_expander`)

## MIDI GPIO fisico (UART)

**Stato:** pianificato — non ancora implementato

### Obiettivo
Ricevere MIDI da porta DIN IN collegata a GPIO 14/15 (31250 bps) tramite optoisolatore (es. 6N138).

### Cosa serve
1. Configurazione UART in `/boot/firmware/config.txt` (`scripts/configure-midi-uart.sh` già pronto)
2. Bridge seriale → ALSA sequencer (es. `ttymidi`, `midi-uart` dtoverlay, o daemon custom)
3. Routing `aconnect` nel orchestratore (`src/midi_orchestrator.py`)
4. Test hardware su Pi 4/5

### Script pronto ma non eseguito dall'installer
`scripts/configure-midi-uart.sh` può essere attivato manualmente quando la funzione sarà implementata.

### UI
Il pannello web elenca solo ingressi attivi (RTP-MIDI, USB); GPIO non è mostrato finché non implementato.

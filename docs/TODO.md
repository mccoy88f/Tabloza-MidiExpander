# Funzionalità pianificate

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
Il pannello web mostra "MIDI GPIO (UART)" con badge **In arrivo**.

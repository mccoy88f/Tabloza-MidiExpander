#!/usr/bin/env python3
"""Tabloza MidiExpander — pannello GPIO opzionale (LED stato + pulsanti fisici).

LED rosso: acceso finché il motore FluidSynth non è pronto (spento a regime).
LED verde: acceso a SoundFont caricato, lampeggia mentre arriva MIDI.
Pulsante 1: All Notes Off (reset synth, come "Stop note" nel pannello web).
Pulsante 2: riavvio motore FluidSynth (come cambio uscita audio/impostazioni).

Disattivato di default — vedi gpio_config.py per l'attivazione in config.json.
"""

import logging
import time

from activity_status import get_audio_activity, get_midi_activity
from event_log import log_event
from fluidsynth_client import read_soundfont_state
from gpio_config import load_gpio_config
from midi_utils import (
    get_midi_status,
    trigger_orchestrator_reload_fluidsynth,
    trigger_orchestrator_stop_notes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [gpio] %(levelname)s: %(message)s",
)
log = logging.getLogger("tabloza.gpio")

POLL_INTERVAL_SEC = 0.15
BLINK_PERIOD_SEC = 0.3


def _engine_ready() -> bool:
    audio = get_audio_activity()
    midi = get_midi_status()
    return bool(audio.get("fluidsynth_running")) and midi.get("fluidsynth") is not None


def _sf2_loaded() -> bool:
    return bool(read_soundfont_state().get("loaded"))


def _all_notes_off():
    log.info("Pulsante: All Notes Off")
    if trigger_orchestrator_stop_notes():
        log_event("gpio", "All Notes Off (pulsante GPIO)")
    else:
        log_event("gpio", "All Notes Off fallito — orchestrator non raggiungibile", "error")


def _restart_engine():
    log.info("Pulsante: riavvio motore FluidSynth")
    if trigger_orchestrator_reload_fluidsynth():
        log_event("gpio", "Riavvio FluidSynth (pulsante GPIO)")
    else:
        log_event("gpio", "Riavvio FluidSynth fallito — orchestrator non raggiungibile", "error")


def main():
    cfg = load_gpio_config()
    if not cfg.get("enabled", False):
        log.info("Pannello GPIO disattivato (config.json → gpio.enabled=false)")
        return

    from gpiozero import Button, LED

    led_ready = LED(cfg["led_ready_pin"], active_high=not cfg["active_low"])
    led_sf2 = LED(cfg["led_sf2_pin"], active_high=not cfg["active_low"])
    btn_stop = Button(cfg["btn_allnotesoff_pin"], pull_up=True, bounce_time=0.05)
    btn_restart = Button(cfg["btn_restart_pin"], pull_up=True, bounce_time=0.05)
    btn_stop.when_pressed = _all_notes_off
    btn_restart.when_pressed = _restart_engine

    log.info(
        "Pannello GPIO attivo — LED ready=GPIO%s sf2=GPIO%s, pulsanti stop=GPIO%s restart=GPIO%s",
        cfg["led_ready_pin"], cfg["led_sf2_pin"],
        cfg["btn_allnotesoff_pin"], cfg["btn_restart_pin"],
    )
    log_event("gpio", "Pannello GPIO avviato")

    blink_on = False
    last_blink = 0.0
    try:
        while True:
            if _engine_ready():
                led_ready.off()
            else:
                led_ready.on()

            if not _sf2_loaded():
                led_sf2.off()
            elif get_midi_activity().get("receiving", False):
                now = time.time()
                if now - last_blink >= BLINK_PERIOD_SEC:
                    blink_on = not blink_on
                    last_blink = now
                led_sf2.on() if blink_on else led_sf2.off()
            else:
                led_sf2.on()

            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

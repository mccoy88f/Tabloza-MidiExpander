#!/usr/bin/env python3
"""Tabloza MidiExpander — MIDI/Audio orchestrator.

Launches FluidSynth, routes RTP-MIDI (rtpmidid) ports to FluidSynth,
reloads on SIGHUP when SoundFont changes.

GPIO UART MIDI: planned — see docs/TODO.md
"""

import json
import logging
import os
import signal
import subprocess
import time
from pathlib import Path

from midi_utils import route_rtpmidi_to_fluidsynth, send_cc7

DATA_DIR = Path(os.environ.get("TABLOZA_DATA_DIR", "/var/lib/tabloza"))
CONFIG_FILE = DATA_DIR / "config.json"
SOUNDFONTS_DIR = DATA_DIR / "soundfonts"

FLUIDSYNTH_BIN = "/usr/bin/fluidsynth"
ROUTING_INTERVAL = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [orchestrator] %(levelname)s: %(message)s",
)
log = logging.getLogger("tabloza.orchestrator")

fluidsynth_proc: subprocess.Popen | None = None
shutdown = False


def load_config() -> dict:
    defaults = {
        "active_soundfont": "",
        "volume": 100,
        "fluidsynth": {
            "audio_driver": "alsa",
            "audio_device": "plughw:0,0",
            "sample_rate": 44100,
            "period_size": 256,
            "period_count": 4,
            "gain": 0.5,
        },
    }
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            stored = json.load(f)
        defaults.update(stored)
        if "fluidsynth" in stored:
            defaults["fluidsynth"].update(stored["fluidsynth"])
    return defaults


def find_soundfont(config: dict) -> Path | None:
    active = config.get("active_soundfont", "")
    if active:
        path = SOUNDFONTS_DIR / active
        if path.is_file():
            return path
    for sf in sorted(SOUNDFONTS_DIR.glob("*.sf2")):
        return sf
    gm = Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")
    return gm if gm.is_file() else None


def build_fluidsynth_cmd(sf_path: Path, config: dict) -> list[str]:
    fs_cfg = config.get("fluidsynth", {})
    return [
        FLUIDSYNTH_BIN,
        "-a", fs_cfg.get("audio_driver", "alsa"),
        "-o", f"audio.alsa.device={fs_cfg.get('audio_device', 'plughw:0,0')}",
        "-r", str(fs_cfg.get("sample_rate", 44100)),
        "-z", str(fs_cfg.get("period_size", 256)),
        "-c", str(fs_cfg.get("period_count", 4)),
        "-g", str(fs_cfg.get("gain", 0.5)),
        "-m", "alsa_seq",
        "-o", "midi.autoconnect=false",
        "-o", "synth.cpu-cores=2",
        "-ni",
        str(sf_path),
    ]


def stop_fluidsynth():
    global fluidsynth_proc
    if fluidsynth_proc and fluidsynth_proc.poll() is None:
        log.info("Arresto FluidSynth (PID %d)", fluidsynth_proc.pid)
        fluidsynth_proc.terminate()
        try:
            fluidsynth_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fluidsynth_proc.kill()
    fluidsynth_proc = None


def apply_volume(config: dict):
    vol = config.get("volume", 100)
    send_cc7(vol)


def start_fluidsynth(config: dict):
    global fluidsynth_proc
    stop_fluidsynth()

    sf = find_soundfont(config)
    if not sf:
        log.error("Nessun SoundFont trovato in %s", SOUNDFONTS_DIR)
        return

    cmd = build_fluidsynth_cmd(sf, config)
    log.info("Avvio FluidSynth con %s", sf.name)
    fluidsynth_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    time.sleep(2)
    route_rtpmidi_to_fluidsynth()
    apply_volume(config)


def handle_sighup(signum, frame):
    log.info("SIGHUP ricevuto — reload SoundFont")
    config = load_config()
    start_fluidsynth(config)


def handle_sigterm(signum, frame):
    global shutdown
    log.info("Arresto orchestratore...")
    shutdown = True
    stop_fluidsynth()


def main():
    signal.signal(signal.SIGHUP, handle_sighup)
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    config = load_config()
    start_fluidsynth(config)

    while not shutdown:
        if fluidsynth_proc and fluidsynth_proc.poll() is not None:
            log.warning("FluidSynth terminato inaspettatamente, riavvio...")
            config = load_config()
            start_fluidsynth(config)
        route_rtpmidi_to_fluidsynth()
        time.sleep(ROUTING_INTERVAL)

    log.info("Orchestratore arrestato.")


if __name__ == "__main__":
    main()

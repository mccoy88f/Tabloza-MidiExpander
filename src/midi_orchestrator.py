#!/usr/bin/env python3
"""Tabloza MidiExpander — MIDI/Audio orchestrator.

Launches FluidSynth, routes hardware serial MIDI and rtpmidid ports,
reloads on SIGHUP when SoundFont changes.
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("TABLOZA_DATA_DIR", "/var/lib/tabloza"))
CONFIG_FILE = DATA_DIR / "config.json"
SOUNDFONTS_DIR = DATA_DIR / "soundfonts"

FLUIDSYNTH_BIN = "/usr/bin/fluidsynth"
SERIAL_PORT = "/dev/serial0"
ROUTING_INTERVAL = 5  # seconds between aconnect retries

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
    return defaults


def find_soundfont(config: dict) -> Path | None:
    active = config.get("active_soundfont", "")
    if active:
        path = SOUNDFONTS_DIR / active
        if path.is_file():
            return path
    # Fallback: first .sf2 in library, then system GM
    for sf in sorted(SOUNDFONTS_DIR.glob("*.sf2")):
        return sf
    gm = Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")
    return gm if gm.is_file() else None


def build_fluidsynth_cmd(sf_path: Path, config: dict) -> list[str]:
    fs_cfg = config.get("fluidsynth", {})
    cmd = [
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
    return cmd


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


def get_midi_ports() -> tuple[list[str], list[str]]:
    """Return (input_ports, output_ports) from aconnect -o."""
    try:
        result = subprocess.run(
            ["aconnect", "-o"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return [], []

    inputs, outputs = [], []
    section = None
    for line in result.stdout.splitlines():
        if "client" in line.lower() and "input" in line.lower():
            section = "in"
            continue
        if "client" in line.lower() and "output" in line.lower():
            section = "out"
            continue
        if line.strip().startswith("'") and section:
            port = line.strip().split()[0]
            if section == "in":
                inputs.append(port)
            else:
                outputs.append(port)
    return inputs, outputs


def find_fluidsynth_input() -> str | None:
    _, outputs = get_midi_ports()
    for port in outputs:
        if "fluidsynth" in port.lower():
            return port
    return None


def find_source_ports() -> list[str]:
    """Find serial MIDI and rtpmidid output ports."""
    _, outputs = get_midi_ports()
    sources = []
    for port in outputs:
        low = port.lower()
        if "serial" in low or "rtpmidid" in low or "midi" in low:
            if "fluidsynth" not in low:
                sources.append(port)
    return sources


def route_midi():
    fs_port = find_fluidsynth_input()
    if not fs_port:
        return

    for src in find_source_ports():
        try:
            subprocess.run(
                ["aconnect", src, fs_port],
                capture_output=True, timeout=3, check=False,
            )
            log.info("Routed %s → %s", src, fs_port)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass


def setup_serial_midi():
    """Expose hardware UART as ALSA sequencer port via aconnect/snd-rtmidi if available."""
    if not Path(SERIAL_PORT).exists():
        return
    try:
        subprocess.run(
            ["stty", "-F", SERIAL_PORT, "31250", "raw", "-echo"],
            capture_output=True, timeout=3, check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


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

    setup_serial_midi()
    config = load_config()
    start_fluidsynth(config)

    while not shutdown:
        if fluidsynth_proc and fluidsynth_proc.poll() is not None:
            log.warning("FluidSynth terminato inaspettatamente, riavvio...")
            config = load_config()
            start_fluidsynth(config)
        route_midi()
        time.sleep(ROUTING_INTERVAL)

    log.info("Orchestratore arrestato.")


if __name__ == "__main__":
    main()

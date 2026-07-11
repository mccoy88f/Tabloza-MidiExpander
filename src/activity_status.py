"""Tabloza — monitor attività MIDI in ingresso e audio in uscita."""

import logging
import re
import subprocess
import time
from pathlib import Path

log = logging.getLogger("tabloza.activity")

MIDI_ACTIVITY_FILE = Path("/run/tabloza/last_midi_event")
MIDI_ACTIVE_WINDOW_SEC = 5.0

_ASEQ_HEADER_PREFIXES = ("Waiting", "Source ", "Destination ", "Subscriber", "Queue ")
_ASEQ_EVENT_RE = re.compile(
    r"(?:Note|Control|Pgm|Pitch|Sustain|Clock|Sys(?:tem)?|Active sensing|Song )",
    re.IGNORECASE,
)


def is_aseqdump_midi_event(line: str) -> bool:
    """True se la riga di aseqdump rappresenta un evento MIDI (non intestazione)."""
    stripped = line.strip()
    if not stripped:
        return False
    if any(stripped.startswith(prefix) for prefix in _ASEQ_HEADER_PREFIXES):
        return False
    if _ASEQ_EVENT_RE.search(stripped):
        return True
    return bool(re.search(r"\d+:\d+\.\d+\s+\d+:\d+\s+", stripped))


def touch_midi_activity():
    """Registra timestamp ultimo evento MIDI ricevuto."""
    MIDI_ACTIVITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MIDI_ACTIVITY_FILE.write_text(f"{time.time():.3f}")


def get_midi_activity() -> dict:
    receiving = False
    seconds_ago = None
    if MIDI_ACTIVITY_FILE.is_file():
        try:
            last = float(MIDI_ACTIVITY_FILE.read_text().strip())
            seconds_ago = max(0.0, time.time() - last)
            receiving = seconds_ago < MIDI_ACTIVE_WINDOW_SEC
        except (ValueError, OSError):
            pass
    return {
        "receiving": receiving,
        "last_event_seconds_ago": round(seconds_ago, 2) if seconds_ago is not None else None,
    }


def _alsa_pcm_running() -> bool:
    """True se un dispositivo ALSA playback è in stato RUNNING."""
    proc = Path("/proc/asound")
    if not proc.is_dir():
        return False
    for status_file in proc.glob("card*/pcm*p/sub*/status"):
        try:
            content = status_file.read_text()
            if "state: RUNNING" in content:
                return True
        except OSError:
            continue
    return False


def get_audio_activity() -> dict:
    fluidsynth_running = False
    try:
        result = subprocess.run(
            ["pgrep", "-x", "fluidsynth"],
            capture_output=True, text=True, timeout=3,
        )
        for pid_str in result.stdout.split():
            try:
                status = Path(f"/proc/{pid_str}/status").read_text()
            except OSError:
                continue
            if "State:" in status and "zombie" not in status.split("State:", 1)[1].lower():
                fluidsynth_running = True
                break
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    output_active = fluidsynth_running and _alsa_pcm_running()

    return {
        "fluidsynth_running": fluidsynth_running,
        "output_active": output_active,
    }

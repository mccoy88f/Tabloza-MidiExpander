"""Tabloza — comandi shell FluidSynth via stdin (pipe persistente)."""

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("tabloza.fluidsynth")

STATE_FILE = Path("/run/tabloza/soundfont_state.json")
_shell_stdin: IO[bytes] | None = None


def _default_state() -> dict:
    return {
        "selected": "",
        "loaded": "",
        "loading": False,
        "error": None,
        "load_started_at": None,
    }


def read_soundfont_state() -> dict:
    if not STATE_FILE.is_file():
        return _default_state()
    try:
        data = json.loads(STATE_FILE.read_text())
        state = _default_state()
        state.update({k: data[k] for k in state if k in data})
        return state
    except (json.JSONDecodeError, OSError):
        return _default_state()


def write_soundfont_state(**kwargs) -> None:
    state = read_soundfont_state()
    state.update(kwargs)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def clear_soundfont_state() -> None:
    write_soundfont_state(**_default_state())


def bind_shell(stdin: IO[bytes] | None) -> None:
    global _shell_stdin
    _shell_stdin = stdin


def shell_bound() -> bool:
    return _shell_stdin is not None


def send_command(command: str) -> tuple[bool, str]:
    if _shell_stdin is None:
        return False, "Shell FluidSynth non disponibile"
    try:
        _shell_stdin.write((command.strip() + "\n").encode())
        _shell_stdin.flush()
        return True, "ok"
    except (OSError, ValueError) as exc:
        return False, str(exc)


def load_timeout_for(path: Path) -> float:
    try:
        size_mb = path.stat().st_size / (1024 * 1024)
    except OSError:
        size_mb = 10
    return min(180.0, max(15.0, 10.0 + size_mb * 0.8))


def load_soundfont(path: Path, process_alive) -> tuple[bool, str]:
    """Invia load e attende. process_alive: callable che ritorna True se fluidsynth è vivo."""
    if not path.is_file():
        return False, f"File non trovato: {path}"
    wait_sec = load_timeout_for(path)
    log.info("Caricamento SF2 %s (attesa %.0fs)", path.name, wait_sec)
    ok, detail = send_command(f"load {path} reset")
    if not ok:
        return ok, detail
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        if not process_alive():
            return False, "FluidSynth terminato durante il caricamento SF2"
        time.sleep(1.0)
    if not process_alive():
        return False, "FluidSynth terminato dopo il caricamento SF2"
    return True, "loaded"


def reset_synth(process_alive) -> tuple[bool, str]:
    ok, detail = send_command("reset")
    if not ok:
        return ok, detail
    time.sleep(0.5)
    if not process_alive():
        return False, "FluidSynth terminato dopo reset"
    return True, "reset"

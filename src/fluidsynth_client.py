"""Tabloza — client TCP per FluidSynth in modalità server (-s)."""

import json
import logging
import socket
from pathlib import Path

log = logging.getLogger("tabloza.fluidsynth")

FLUID_HOST = "127.0.0.1"
FLUID_PORT = 9800
STATE_FILE = Path("/run/tabloza/soundfont_state.json")


def _default_state() -> dict:
    return {
        "selected": "",
        "loaded": "",
        "loading": False,
        "error": None,
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


def send_command(command: str, timeout: float = 10.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((FLUID_HOST, FLUID_PORT), timeout=timeout) as sock:
            sock.sendall((command.strip() + "\n").encode())
            sock.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
            response = b"".join(chunks).decode("utf-8", errors="replace").strip()
            lowered = response.lower()
            if "error" in lowered or "failed" in lowered:
                return False, response or command
            return True, response
    except OSError as exc:
        return False, str(exc)


def server_ready() -> bool:
    ok, _ = send_command("help", timeout=2.0)
    return ok


def load_timeout_for(path: Path) -> float:
    try:
        size_mb = path.stat().st_size / (1024 * 1024)
    except OSError:
        size_mb = 10
    return min(180.0, max(30.0, 20.0 + size_mb * 0.8))


def load_soundfont(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"File non trovato: {path}"
    timeout = load_timeout_for(path)
    log.info("Caricamento SF2 %s (timeout %.0fs)", path.name, timeout)
    return send_command(f'load "{path}" reset', timeout=timeout)


def reset_synth() -> tuple[bool, str]:
    return send_command("reset", timeout=5.0)

"""Tabloza — comandi shell FluidSynth via stdin (pipe persistente)."""

import json
import logging
import re
import time
from pathlib import Path

log = logging.getLogger("tabloza.fluidsynth")

STATE_FILE = Path("/run/tabloza/soundfont_state.json")
CANCEL_LOAD_FLAG = Path("/run/tabloza/cancel_soundfont_load")
FLUIDSYNTH_LOG = Path("/run/tabloza/fluidsynth.log")
_shell_stdin = None

_FONT_ENTRY_RE = re.compile(r"^\s*(\d+)\s+(\S.*)$")


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


def request_cancel_soundfont_load() -> None:
    CANCEL_LOAD_FLAG.parent.mkdir(parents=True, exist_ok=True)
    CANCEL_LOAD_FLAG.write_text("1")


def cancel_soundfont_load_requested() -> bool:
    return CANCEL_LOAD_FLAG.is_file()


def clear_cancel_soundfont_load() -> None:
    CANCEL_LOAD_FLAG.unlink(missing_ok=True)


def bind_shell(stdin) -> None:
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


def _log_file_size() -> int:
    try:
        return FLUIDSYNTH_LOG.stat().st_size
    except OSError:
        return 0


def _read_fluidsynth_log_since(offset: int) -> str:
    if not FLUIDSYNTH_LOG.is_file():
        return ""
    try:
        with open(FLUIDSYNTH_LOG, encoding="utf-8", errors="replace") as handle:
            handle.seek(max(0, offset))
            return handle.read()
    except OSError:
        return ""


def parse_font_ids_from_log(text: str) -> list[int]:
    """Parse `fonts` shell output (ID / Name rows) from FluidSynth log text."""
    ids: list[int] = []
    past_header = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        if re.match(r"^ID\s+Name", stripped, re.IGNORECASE):
            past_header = True
            continue
        if "no soundfont" in stripped.lower():
            continue
        match = _FONT_ENTRY_RE.match(stripped)
        if match and (past_header or "/" in match.group(2) or match.group(2).endswith(".sf2")):
            ids.append(int(match.group(1)))
    return ids


def query_loaded_font_ids() -> list[int]:
    """Return SoundFont IDs currently loaded in FluidSynth."""
    if _shell_stdin is None:
        return []
    offset = _log_file_size()
    ok, _ = send_command("fonts")
    if not ok:
        return []
    time.sleep(0.25)
    return parse_font_ids_from_log(_read_fluidsynth_log_since(offset))


def unload_all_soundfonts(
    process_alive,
    should_cancel=None,
    max_rounds: int = 8,
) -> tuple[bool, str]:
    """Unload every SoundFont from FluidSynth and reset MIDI state."""
    if _shell_stdin is None:
        return False, "Shell FluidSynth non disponibile"

    total = 0
    for _round in range(max_rounds):
        if should_cancel and should_cancel():
            return False, "cancelled"
        if not process_alive():
            return False, "FluidSynth terminato durante unload"

        font_ids = query_loaded_font_ids()
        if not font_ids:
            break

        for font_id in sorted(font_ids, reverse=True):
            if should_cancel and should_cancel():
                return False, "cancelled"
            if not process_alive():
                return False, "FluidSynth terminato durante unload"
            ok, detail = send_command(f"unload {font_id}")
            if not ok:
                return ok, detail
            time.sleep(0.15)
            total += 1

    send_command("reset")
    time.sleep(0.15)
    if not process_alive():
        return False, "FluidSynth terminato dopo unload"
    if total:
        log.info("Scaricati %d SoundFont da FluidSynth", total)
    return True, "unloaded"


def load_timeout_for(path: Path) -> float:
    try:
        size_mb = path.stat().st_size / (1024 * 1024)
    except OSError:
        size_mb = 10
    return min(180.0, max(15.0, 10.0 + size_mb * 0.8))


def load_soundfont(
    path: Path,
    process_alive,
    should_cancel=None,
) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"File non trovato: {path}"
    if should_cancel and should_cancel():
        return False, "cancelled"
    ok, detail = unload_all_soundfonts(process_alive, should_cancel=should_cancel)
    if not ok:
        return ok, detail
    if detail == "cancelled":
        return False, "cancelled"
    try:
        size_mb = path.stat().st_size / (1024 * 1024)
    except OSError:
        size_mb = 10
    wait_sec = load_timeout_for(path)
    log.info("Caricamento SF2 %s (attesa %.0fs)", path.name, wait_sec)
    ok, detail = send_command(f"load {path} reset")
    if not ok:
        return ok, detail
    if should_cancel and should_cancel():
        unload_all_soundfonts(process_alive, should_cancel=should_cancel)
        return False, "cancelled"
    settle = min(wait_sec, max(8.0, size_mb * 0.15))
    log.info("Attesa stabilizzazione SF2 %.0fs", settle)
    deadline = time.time() + settle
    while time.time() < deadline:
        if should_cancel and should_cancel():
            unload_all_soundfonts(process_alive, should_cancel=should_cancel)
            return False, "cancelled"
        if not process_alive():
            return False, "FluidSynth terminato durante il caricamento SF2"
        time.sleep(0.25)
    if should_cancel and should_cancel():
        unload_all_soundfonts(process_alive, should_cancel=should_cancel)
        return False, "cancelled"
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


def apply_runtime_synth_settings(fs_cfg: dict) -> tuple[bool, str]:
    """Apply synth settings that can change without full restart (best-effort)."""
    from synth_config import merge_fluidsynth_config

    cfg = merge_fluidsynth_config(fs_cfg)
    commands = [
        f"set synth.polyphony {cfg['polyphony']}",
        f"set synth.reverb.active {1 if cfg['reverb'] else 0}",
        f"set synth.chorus.active {1 if cfg['chorus'] else 0}",
    ]
    if _shell_stdin is None:
        return False, "Shell FluidSynth non disponibile"
    for cmd in commands:
        ok, detail = send_command(cmd)
        if not ok:
            return False, detail
    return True, "ok"

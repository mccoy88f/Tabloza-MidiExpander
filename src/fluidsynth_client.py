"""Tabloza — comandi shell FluidSynth via stdin (pipe persistente)."""

import json
import logging
import re
import shlex
import time
from pathlib import Path

log = logging.getLogger("tabloza.fluidsynth")

STATE_FILE = Path("/run/tabloza/soundfont_state.json")
CANCEL_LOAD_FLAG = Path("/run/tabloza/cancel_soundfont_load")
FLUIDSYNTH_LOG = Path("/run/tabloza/fluidsynth.log")
_shell_stdin = None

_FONT_ENTRY_RE = re.compile(r"^\s*(\d+)\s+(\S.*)$")
_LOAD_ERROR_HINTS = (
    "failed to load soundfont",
    "failed to load",
    "unable to open file",
    "unable to open",
    "out of memory",
    "not a riff file",
    "ipatch_file_open",
)


def _default_state() -> dict:
    return {
        "selected": "",
        "loaded": "",
        "loading": False,
        "error": None,
        "load_started_at": None,
        "load_progress": None,
        "load_ram_baseline_mb": None,
        "load_expected_mb": None,
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


def soundfont_path_matches(path: Path, font_ref: str) -> bool:
    """True if a FluidSynth `fonts` row refers to the given SF2 path."""
    ref = font_ref.strip().strip("'\"")
    if not ref:
        return False
    try:
        if path.resolve() == Path(ref).resolve():
            return True
    except OSError:
        pass
    return path.name.lower() == Path(ref).name.lower()


def parse_fonts_from_log(text: str) -> list[dict]:
    """Parse `fonts` shell output (ID / Name rows) from FluidSynth log text."""
    fonts: list[dict] = []
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
        if match and (
            past_header
            or "/" in match.group(2)
            or match.group(2).lower().endswith(".sf2")
        ):
            fonts.append({"id": int(match.group(1)), "path": match.group(2).strip()})
    return fonts


def parse_font_ids_from_log(text: str) -> list[int]:
    return [font["id"] for font in parse_fonts_from_log(text)]


def parse_load_error_from_log(text: str) -> str | None:
    """Return first FluidSynth load error line found in log text."""
    for line in text.splitlines():
        lower = line.lower()
        if "fluidsynth:" in lower and "error" in lower:
            if "soundfont" in lower or any(hint in lower for hint in _LOAD_ERROR_HINTS):
                return line.strip()
        if any(hint in lower for hint in _LOAD_ERROR_HINTS):
            return line.strip()
    return None


def _load_shell_ready(chunk: str) -> bool:
    if re.search(r"^>\s*$", chunk, re.MULTILINE):
        return True
    return "loaded soundfont" in chunk.lower()


def query_loaded_fonts() -> list[dict]:
    """Return SoundFonts currently on the FluidSynth stack."""
    if _shell_stdin is None:
        return []
    offset = _log_file_size()
    ok, _ = send_command("fonts")
    if not ok:
        return []
    time.sleep(0.3)
    return parse_fonts_from_log(_read_fluidsynth_log_since(offset))


def query_loaded_font_ids() -> list[int]:
    return [font["id"] for font in query_loaded_fonts()]


def is_path_in_loaded_fonts(path: Path, fonts: list[dict]) -> bool:
    return any(soundfont_path_matches(path, font["path"]) for font in fonts)


def verify_soundfont_loaded(path: Path) -> tuple[bool, str]:
    """Confirm that the given SF2 is present on FluidSynth's stack."""
    if not path.is_file():
        return False, f"File non trovato: {path.name}"

    tail = _read_fluidsynth_log_since(max(0, _log_file_size() - 16384))
    err = parse_load_error_from_log(tail)
    if err:
        return False, err

    fonts = query_loaded_fonts()
    if not fonts:
        return False, "Nessun SoundFont nello stack FluidSynth"
    if is_path_in_loaded_fonts(path, fonts):
        return True, "ok"

    loaded_names = ", ".join(Path(font["path"]).name for font in fonts)
    return False, f"Atteso {path.name}, stack FluidSynth: {loaded_names or '—'}"


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
    return min(600.0, max(25.0, 20.0 + size_mb * 1.5))


def _file_size_mb(path: Path) -> float:
    try:
        return path.stat().st_size / (1024 * 1024)
    except OSError:
        return 0.0


def estimate_sf2_load_progress(baseline_mb: float, expected_mb: float) -> int:
    """Estimate SF2 load % from FluidSynth RSS growth vs file size (capped at 99)."""
    if expected_mb <= 0:
        return 0
    from system_stats import fluidsynth_rss_mb

    current = fluidsynth_rss_mb()
    if current is None:
        return 0
    delta = max(0.0, float(current) - baseline_mb)
    pct = int(100.0 * delta / expected_mb)
    return min(99, max(0, pct))


def _update_load_progress_from_ram(baseline_mb: float, expected_mb: float) -> int:
    progress = estimate_sf2_load_progress(baseline_mb, expected_mb)
    write_soundfont_state(load_progress=progress)
    return progress


def _clear_load_progress_fields() -> dict:
    return {
        "load_progress": None,
        "load_ram_baseline_mb": None,
        "load_expected_mb": None,
    }


def _wait_for_load_completion(
    log_offset: int,
    deadline: float,
    process_alive,
    should_cancel=None,
    *,
    ram_baseline_mb: float = 0.0,
    ram_expected_mb: float = 0.0,
) -> tuple[bool, str | None]:
    """Wait until FluidSynth finishes processing `load` or deadline expires."""
    saw_log_activity = False
    last_log_growth = time.time()

    while time.time() < deadline:
        if should_cancel and should_cancel():
            return False, "cancelled"
        if not process_alive():
            return False, "FluidSynth terminato durante il caricamento SF2"

        if ram_expected_mb > 0:
            _update_load_progress_from_ram(ram_baseline_mb, ram_expected_mb)

        chunk = _read_fluidsynth_log_since(log_offset)
        err = parse_load_error_from_log(chunk)
        if err:
            return False, err

        if chunk:
            saw_log_activity = True
            last_log_growth = time.time()

        if _load_shell_ready(chunk):
            return True, None

        if saw_log_activity and time.time() - last_log_growth >= 2.0:
            return True, None

        time.sleep(0.4)

    return True, None


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

    from system_stats import fluidsynth_rss_mb

    baseline_mb = float(fluidsynth_rss_mb() or 0)
    expected_mb = _file_size_mb(path)
    write_soundfont_state(
        load_progress=0,
        load_ram_baseline_mb=round(baseline_mb, 1),
        load_expected_mb=round(expected_mb, 1),
    )

    wait_sec = load_timeout_for(path)
    log_offset = _log_file_size()
    log.info(
        "Caricamento SF2 %s (verifica fino a %.0fs, baseline RAM %.0f MB, file %.0f MB)",
        path.name, wait_sec, baseline_mb, expected_mb,
    )
    ok, detail = send_command(f"load {shlex.quote(str(path))} reset")
    if not ok:
        write_soundfont_state(**_clear_load_progress_fields())
        return ok, detail
    if should_cancel and should_cancel():
        unload_all_soundfonts(process_alive, should_cancel=should_cancel)
        write_soundfont_state(**_clear_load_progress_fields())
        return False, "cancelled"

    deadline = time.time() + wait_sec
    completed, wait_detail = _wait_for_load_completion(
        log_offset,
        deadline,
        process_alive,
        should_cancel=should_cancel,
        ram_baseline_mb=baseline_mb,
        ram_expected_mb=expected_mb,
    )
    if not completed:
        write_soundfont_state(**_clear_load_progress_fields())
        if wait_detail == "cancelled":
            unload_all_soundfonts(process_alive, should_cancel=should_cancel)
            return False, "cancelled"
        unload_all_soundfonts(process_alive, should_cancel=should_cancel)
        return False, f"Caricamento fallito: {wait_detail}"

    for attempt in range(5):
        if should_cancel and should_cancel():
            unload_all_soundfonts(process_alive, should_cancel=should_cancel)
            write_soundfont_state(**_clear_load_progress_fields())
            return False, "cancelled"
        if not process_alive():
            write_soundfont_state(**_clear_load_progress_fields())
            return False, "FluidSynth terminato dopo il caricamento SF2"

        if expected_mb > 0:
            _update_load_progress_from_ram(baseline_mb, expected_mb)

        chunk = _read_fluidsynth_log_since(log_offset)
        err = parse_load_error_from_log(chunk)
        if err:
            unload_all_soundfonts(process_alive, should_cancel=should_cancel)
            write_soundfont_state(**_clear_load_progress_fields())
            return False, f"Caricamento fallito: {err}"

        fonts = query_loaded_fonts()
        if is_path_in_loaded_fonts(path, fonts):
            log.info("SF2 verificato nello stack FluidSynth: %s", path.name)
            write_soundfont_state(**_clear_load_progress_fields())
            return True, "loaded"

        if attempt < 4:
            time.sleep(0.5)

    unload_all_soundfonts(process_alive, should_cancel=should_cancel)
    write_soundfont_state(**_clear_load_progress_fields())
    return False, (
        f"SoundFont {path.name} non presente in FluidSynth dopo {int(wait_sec)}s — "
        "controlla /run/tabloza/fluidsynth.log"
    )


def reset_synth(process_alive) -> tuple[bool, str]:
    ok, detail = send_command("reset")
    if not ok:
        return ok, detail
    time.sleep(0.5)
    if not process_alive():
        return False, "FluidSynth terminato dopo reset"
    return True, "reset"


EFFECT_SETTING_KEYS = (
    "synth.reverb.active",
    "synth.reverb.room-size",
    "synth.reverb.damp",
    "synth.reverb.width",
    "synth.reverb.level",
    "synth.chorus.active",
    "synth.chorus.nr",
    "synth.chorus.level",
    "synth.chorus.speed",
    "synth.chorus.depth",
)


def _parse_get_settings_from_log(text: str) -> dict[str, str]:
    """Parse FluidSynth shell `get synth.*` responses from log text."""
    out: dict[str, str] = {}
    lines = text.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        match = re.match(r"^> get (synth\.\S+)$", line)
        if match and idx + 1 < len(lines):
            value = lines[idx + 1].strip()
            if value and not value.startswith(">"):
                key = match.group(1).removeprefix("synth.").replace("-", "_")
                out[key] = value
                idx += 2
                continue
        idx += 1
    return out


def query_effect_settings() -> dict[str, str]:
    """Read current FluidSynth reverb/chorus parameters from the live shell."""
    if _shell_stdin is None:
        return {}
    offset = _log_file_size()
    for key in EFFECT_SETTING_KEYS:
        ok, _ = send_command(f"get {key}")
        if not ok:
            return {}
        time.sleep(0.08)
    return _parse_get_settings_from_log(_read_fluidsynth_log_since(offset))


def apply_runtime_synth_settings(fs_cfg: dict) -> tuple[bool, str]:
    """Apply synth settings that can change without full restart (best-effort)."""
    from synth_config import fluidsynth_effect_set_commands, merge_fluidsynth_config

    cfg = merge_fluidsynth_config(fs_cfg)
    commands = [f"set synth.polyphony {cfg['polyphony']}"]
    commands.extend(fluidsynth_effect_set_commands(cfg))
    if _shell_stdin is None:
        return False, "Shell FluidSynth non disponibile"
    for cmd in commands:
        ok, detail = send_command(cmd)
        if not ok:
            return False, detail
    return True, "ok"

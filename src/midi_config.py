"""Tabloza — impostazioni MIDI (banchi FluidSynth, buffer anti-jitter RTP)."""

DEFAULT_MIDI_JITTER_BUFFER_MS = 25
MIN_MIDI_JITTER_BUFFER_MS = 0
MAX_MIDI_JITTER_BUFFER_MS = 150

DEFAULT_MIDI_BANK_SELECT = "gs"
MIDI_BANK_SELECT_MODES = ("gm", "gs", "xg", "mma")

DEFAULT_MIDI_CONFIG: dict = {
    "jitter_buffer_ms": DEFAULT_MIDI_JITTER_BUFFER_MS,
    "jitter_buffer_enabled": True,
    "sysex_bank_auto": True,
    "bank_select": DEFAULT_MIDI_BANK_SELECT,
}


def normalize_bank_select(value) -> str:
    mode = str(value or DEFAULT_MIDI_BANK_SELECT).strip().lower()
    if mode not in MIDI_BANK_SELECT_MODES:
        return DEFAULT_MIDI_BANK_SELECT
    return mode


def merge_midi_config(stored: dict | None) -> dict:
    merged = dict(DEFAULT_MIDI_CONFIG)
    if stored:
        merged.update(stored)
    merged["jitter_buffer_ms"] = normalize_jitter_buffer_ms(merged.get("jitter_buffer_ms"))
    merged["jitter_buffer_enabled"] = bool(merged.get("jitter_buffer_enabled", True))
    merged["sysex_bank_auto"] = bool(merged.get("sysex_bank_auto", True))
    merged["bank_select"] = normalize_bank_select(merged.get("bank_select"))
    return merged


def normalize_jitter_buffer_ms(value) -> int:
    try:
        ms = int(value)
    except (TypeError, ValueError):
        ms = DEFAULT_MIDI_JITTER_BUFFER_MS
    return max(MIN_MIDI_JITTER_BUFFER_MS, min(MAX_MIDI_JITTER_BUFFER_MS, ms))


def is_jitter_buffer_enabled(config: dict) -> bool:
    midi = config.get("midi")
    if isinstance(midi, dict) and "jitter_buffer_enabled" in midi:
        return bool(midi["jitter_buffer_enabled"])
    return True


def is_sysex_bank_auto_enabled(config: dict) -> bool:
    midi = config.get("midi")
    if isinstance(midi, dict) and "sysex_bank_auto" in midi:
        return bool(midi["sysex_bank_auto"])
    return True


def get_jitter_buffer_ms(config: dict) -> int:
    if not is_jitter_buffer_enabled(config):
        return 0
    midi = config.get("midi")
    if isinstance(midi, dict):
        return normalize_jitter_buffer_ms(midi.get("jitter_buffer_ms"))
    return DEFAULT_MIDI_JITTER_BUFFER_MS


def get_midi_bank_select(config: dict) -> str:
    midi = config.get("midi")
    if isinstance(midi, dict):
        return normalize_bank_select(midi.get("bank_select"))
    return DEFAULT_MIDI_BANK_SELECT


def midi_settings_for_api(config: dict) -> dict:
    from midi_jitter_buffer import jitter_buffer_status

    from midi_sysex_mode import get_runtime_bank_select

    midi = merge_midi_config(config.get("midi") if isinstance(config.get("midi"), dict) else None)
    status = jitter_buffer_status()
    return {
        "bank_select": midi["bank_select"],
        "bank_select_modes": list(MIDI_BANK_SELECT_MODES),
        "runtime_bank_select": get_runtime_bank_select(midi["bank_select"]),
        "jitter_buffer_enabled": midi["jitter_buffer_enabled"],
        "jitter_buffer_ms": midi["jitter_buffer_ms"],
        "sysex_bank_auto": midi["sysex_bank_auto"],
        "jitter_buffer_active": status["active"],
        "jitter_buffer_effective_ms": status["buffer_ms"] if status["active"] else 0,
        "rtmidi_available": status["rtmidi_available"],
    }


def parse_midi_settings_update(data: dict, current: dict) -> tuple[dict, bool, bool]:
    """Return merged midi config, fluidsynth restart needed, buffer refresh needed."""
    midi = merge_midi_config(current.get("midi"))
    old_bank = midi["bank_select"]
    old_buffer_enabled = midi["jitter_buffer_enabled"]
    old_buffer_ms = midi["jitter_buffer_ms"]
    old_sysex_auto = midi["sysex_bank_auto"]

    if "bank_select" in data:
        midi["bank_select"] = normalize_bank_select(data["bank_select"])
    if "jitter_buffer_enabled" in data:
        midi["jitter_buffer_enabled"] = bool(data["jitter_buffer_enabled"])
    if "sysex_bank_auto" in data:
        midi["sysex_bank_auto"] = bool(data["sysex_bank_auto"])
    if "jitter_buffer_ms" in data:
        midi["jitter_buffer_ms"] = normalize_jitter_buffer_ms(data["jitter_buffer_ms"])

    needs_restart = midi["bank_select"] != old_bank
    needs_buffer = (
        midi["jitter_buffer_enabled"] != old_buffer_enabled
        or midi["jitter_buffer_ms"] != old_buffer_ms
        or midi["sysex_bank_auto"] != old_sysex_auto
    )
    return midi, needs_restart, needs_buffer

"""Tabloza — impostazioni MIDI (buffer anti-jitter RTP)."""

DEFAULT_MIDI_JITTER_BUFFER_MS = 25
MIN_MIDI_JITTER_BUFFER_MS = 0
MAX_MIDI_JITTER_BUFFER_MS = 150

DEFAULT_MIDI_CONFIG: dict = {
    "jitter_buffer_ms": DEFAULT_MIDI_JITTER_BUFFER_MS,
}


def merge_midi_config(stored: dict | None) -> dict:
    merged = dict(DEFAULT_MIDI_CONFIG)
    if stored:
        merged.update(stored)
    merged["jitter_buffer_ms"] = normalize_jitter_buffer_ms(merged.get("jitter_buffer_ms"))
    return merged


def normalize_jitter_buffer_ms(value) -> int:
    try:
        ms = int(value)
    except (TypeError, ValueError):
        ms = DEFAULT_MIDI_JITTER_BUFFER_MS
    return max(MIN_MIDI_JITTER_BUFFER_MS, min(MAX_MIDI_JITTER_BUFFER_MS, ms))


def get_jitter_buffer_ms(config: dict) -> int:
    midi = config.get("midi")
    if isinstance(midi, dict):
        return normalize_jitter_buffer_ms(midi.get("jitter_buffer_ms"))
    return DEFAULT_MIDI_JITTER_BUFFER_MS

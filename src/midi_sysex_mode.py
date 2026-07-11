"""Tabloza — rilevamento SysEx GM/GS/XG/MMA e cambio runtime bank-select."""

from __future__ import annotations

import logging
import threading

from midi_config import MIDI_BANK_SELECT_MODES, normalize_bank_select

log = logging.getLogger("tabloza.midi.sysex")

SYSEX_DEVICE_BROADCAST = 0x7F
SYSEX_UNIV_NON_REALTIME = 0x7E
SYSEX_GM_ID = 0x09
SYSEX_GM_ON = 0x01
SYSEX_GM2_ON = 0x03
SYSEX_MANUF_ROLAND = 0x41
SYSEX_GS_MODEL = 0x42
SYSEX_GS_DT1 = 0x12
SYSEX_MANUF_YAMAHA = 0x43
SYSEX_XG_MODEL = 0x4C

_runtime_lock = threading.Lock()
_runtime_bank_select: str | None = None


def reset_runtime_bank_select(default_mode: str) -> None:
    global _runtime_bank_select
    with _runtime_lock:
        _runtime_bank_select = normalize_bank_select(default_mode)


def get_runtime_bank_select(fallback: str = "gs") -> str:
    with _runtime_lock:
        if _runtime_bank_select:
            return _runtime_bank_select
    return normalize_bank_select(fallback)


def _device_matches(message_device: int, synth_device_id: int = SYSEX_DEVICE_BROADCAST) -> bool:
    return (
        message_device == synth_device_id
        or message_device == SYSEX_DEVICE_BROADCAST
        or synth_device_id == SYSEX_DEVICE_BROADCAST
    )


def detect_bank_mode_from_sysex(payload: bytes) -> str | None:
    """Return gm/gs/xg/mma if payload is a known mode SysEx (without F0/F7)."""
    if len(payload) < 4:
        return None
    dev = payload[1]

    if payload[0] == SYSEX_UNIV_NON_REALTIME and _device_matches(dev):
        if len(payload) >= 4 and payload[2] == SYSEX_GM_ID:
            if payload[3] == SYSEX_GM_ON:
                return "gm"
            if payload[3] == SYSEX_GM2_ON:
                return "mma"

    if (
        len(payload) >= 8
        and payload[0] == SYSEX_MANUF_ROLAND
        and _device_matches(dev)
        and payload[2] == SYSEX_GS_MODEL
        and payload[3] == SYSEX_GS_DT1
    ):
        addr = (payload[4] << 16) | (payload[5] << 8) | payload[6]
        if addr == 0x40007F and len(payload) >= 9:
            if payload[7] == 0x00:
                return "gs"
            if payload[7] == 0x7F:
                return "gm"

    if (
        len(payload) >= 7
        and payload[0] == SYSEX_MANUF_YAMAHA
        and _device_matches(dev)
        and payload[2] == SYSEX_XG_MODEL
    ):
        addr = (payload[3] << 16) | (payload[4] << 8) | payload[5]
        if addr in (0x00007E, 0x00007F) and len(payload) >= 7 and payload[6] == 0x00:
            return "xg"

    return None


def _sysex_payload_from_message(message: tuple | list) -> bytes | None:
    if not message or message[0] != 0xF0:
        return None
    end = len(message)
    if message[-1] == 0xF7:
        end -= 1
    if end <= 1:
        return None
    return bytes(message[1:end])


def apply_runtime_bank_select(mode: str, *, reset_synth: bool = True) -> bool:
    """Apply bank-select to FluidSynth shell; update runtime state."""
    mode = normalize_bank_select(mode)
    with _runtime_lock:
        global _runtime_bank_select
        if _runtime_bank_select == mode and not reset_synth:
            return True
    from fluidsynth_client import send_command, shell_bound

    if not shell_bound():
        log.debug("SysEx %s ignorato — shell FluidSynth non pronta", mode)
        return False
    ok, detail = send_command(f"set synth.midi-bank-select {mode}")
    if not ok:
        log.warning("SysEx → bank %s fallito: %s", mode, detail)
        return False
    if reset_synth:
        send_command("reset")
    with _runtime_lock:
        _runtime_bank_select = mode
    log.info("SysEx → modalità banchi %s (runtime)", mode.upper())
    try:
        from event_log import log_event
        log_event("orchestrator", f"SysEx: modalità banchi → {mode.upper()}")
    except ImportError:
        pass
    return True


def maybe_apply_sysex_bank_mode(message: tuple | list) -> bool:
    """Inspect MIDI message; apply bank mode if mode SysEx. Returns True if consumed."""
    payload = _sysex_payload_from_message(message)
    if not payload:
        return False
    mode = detect_bank_mode_from_sysex(payload)
    if not mode or mode not in MIDI_BANK_SELECT_MODES:
        return False
    apply_runtime_bank_select(mode)
    return True

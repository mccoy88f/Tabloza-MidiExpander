"""Tabloza — compatibilità python-rtmidi (evita il pacchetto PyPI omonimo 'rtmidi')."""

from __future__ import annotations

try:
    import rtmidi
except ImportError:
    rtmidi = None


def alsa_rtmidi_api():
    """Return the ALSA API constant for python-rtmidi, or None for default backend."""
    if rtmidi is None:
        return None
    for name in ("API_UNIX_ALSA", "API_LINUX_ALSA", "UNIX_ALSA", "LINUX_ALSA"):
        api = getattr(rtmidi, name, None)
        if api is not None:
            return api
    return getattr(rtmidi, "API_UNSPECIFIED", None)


def is_usable_python_rtmidi() -> bool:
    """True if the imported module is python-rtmidi, not the conflicting 'rtmidi' package."""
    if rtmidi is None:
        return False
    if not hasattr(rtmidi, "MidiIn") or not hasattr(rtmidi, "MidiOut"):
        return False
    if alsa_rtmidi_api() is not None:
        return True
    try:
        probe = rtmidi.MidiIn()
    except Exception:
        return False
    return callable(getattr(probe, "open_virtual_port", None))


def configure_midi_in(midi_in) -> None:
    """Keep SysEx; ignore timing/active sensing when the binding supports it."""
    try:
        midi_in.ignore_types(sysex=False, timing=False, active_sensing=False)
    except TypeError:
        try:
            midi_in.ignore_types(sysex=False, timing=False)
        except TypeError:
            try:
                midi_in.ignore_types(False, False, False)
            except TypeError:
                pass


def make_midi_in():
    if rtmidi is None:
        raise RuntimeError("python-rtmidi non installato")
    api = alsa_rtmidi_api()
    if api is not None:
        return rtmidi.MidiIn(api)
    return rtmidi.MidiIn()


def make_midi_out():
    if rtmidi is None:
        raise RuntimeError("python-rtmidi non installato")
    api = alsa_rtmidi_api()
    if api is not None:
        return rtmidi.MidiOut(api)
    return rtmidi.MidiOut()


def rtmidi_diagnostic() -> str:
    if rtmidi is None:
        return "installa python-rtmidi (pip install python-rtmidi)"
    if is_usable_python_rtmidi():
        return "ok"
    mod_path = getattr(rtmidi, "__file__", "?")
    return (
        f"modulo rtmidi non compatibile ({mod_path}) — "
        "pip uninstall -y rtmidi rtmidi-python && "
        "pip install --break-system-packages 'python-rtmidi>=1.4.9'"
    )

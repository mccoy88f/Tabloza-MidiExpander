"""SoundFont selection helpers (no heavy deps — testable)."""

import os
from pathlib import Path

SOUNDFONTS_DIR = Path(os.environ.get("TABLOZA_DATA_DIR", "/var/lib/tabloza")) / "soundfonts"


def coerce_default_soundfont(raw) -> str:
    """Normalize config value to a single default SF2 filename (legacy-safe)."""
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                return item.strip()
        return ""
    if isinstance(raw, str):
        return raw.strip()
    return ""


def resolve_default_soundfont(
    config: dict,
    soundfonts_dir: Path | None = None,
) -> str:
    """Return the single configured default if the file exists, else empty."""
    root = soundfonts_dir or SOUNDFONTS_DIR
    name = coerce_default_soundfont(config.get("default_soundfont", ""))
    if name and (root / name).is_file():
        return name
    return ""


def set_default_soundfont(config: dict, name: str | None) -> dict:
    """Set or clear the only startup default SoundFont."""
    updated = dict(config)
    if name:
        updated["default_soundfont"] = name.strip()
    else:
        updated["default_soundfont"] = ""
    return updated


def startup_soundfont_name(config: dict, soundfonts_dir: Path | None = None) -> str:
    """SoundFont to load at boot / after FluidSynth restart."""
    root = soundfonts_dir or SOUNDFONTS_DIR
    default = resolve_default_soundfont(config, root)
    if default:
        return default
    active = config.get("active_soundfont", "")
    if active and (root / active).is_file():
        return active
    return ""

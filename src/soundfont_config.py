"""SoundFont selection helpers (no heavy deps — testable)."""

import os
from pathlib import Path

SOUNDFONTS_DIR = Path(os.environ.get("TABLOZA_DATA_DIR", "/var/lib/tabloza")) / "soundfonts"


def startup_soundfont_name(config: dict, soundfonts_dir: Path | None = None) -> str:
    """SoundFont to load at boot / after FluidSynth restart."""
    root = soundfonts_dir or SOUNDFONTS_DIR
    default = config.get("default_soundfont", "")
    if default and (root / default).is_file():
        return default
    active = config.get("active_soundfont", "")
    if active and (root / active).is_file():
        return active
    return ""

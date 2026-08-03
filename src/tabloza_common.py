"""Tabloza MidiExpander — shared utilities."""

import json
import os
import secrets
from pathlib import Path

import bcrypt

HOSTNAME = "tabloza-me"
MDNS_NAME = f"{HOSTNAME}.local"
GITHUB_URL = "https://github.com/mccoy88f/Tabloza-MidiExpander"
AUTHOR = "mccoy88f"
VERSION_FILE = Path("/opt/tabloza/VERSION")


def get_version() -> str:
    if VERSION_FILE.is_file():
        return VERSION_FILE.read_text().strip()
    return "dev"

DATA_DIR = Path(os.environ.get("TABLOZA_DATA_DIR", "/var/lib/tabloza"))
CONFIG_FILE = DATA_DIR / "config.json"
AUTH_FILE = DATA_DIR / "auth.json"
SECRET_FILE = DATA_DIR / "secret.key"
SOUNDFONTS_DIR = DATA_DIR / "soundfonts"


def startup_soundfont_name(config: dict, soundfonts_dir: Path | None = None) -> str:
    from soundfont_config import startup_soundfont_name as _name

    return _name(config, soundfonts_dir or SOUNDFONTS_DIR)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    else:
        config = {"active_soundfont": "", "default_soundfont": "", "volume": 100}
    from audio_utils import normalize_volume
    if "volume" in config:
        config["volume"] = normalize_volume(config["volume"])
    return config


def save_config(config: dict):
    existing = load_config() if CONFIG_FILE.exists() else {}
    merged = {**existing, **config}
    existing_fs = existing.get("fluidsynth") if isinstance(existing.get("fluidsynth"), dict) else {}
    incoming_fs = config.get("fluidsynth") if isinstance(config.get("fluidsynth"), dict) else None
    if incoming_fs is not None:
        merged["fluidsynth"] = {**existing_fs, **incoming_fs}
    elif existing_fs:
        merged["fluidsynth"] = existing_fs
    existing_midi = existing.get("midi") if isinstance(existing.get("midi"), dict) else {}
    incoming_midi = config.get("midi") if isinstance(config.get("midi"), dict) else None
    if incoming_midi is not None:
        merged["midi"] = {**existing_midi, **incoming_midi}
    elif existing_midi:
        merged["midi"] = existing_midi
    existing_network = existing.get("network") if isinstance(existing.get("network"), dict) else {}
    incoming_network = config.get("network") if isinstance(config.get("network"), dict) else None
    if incoming_network is not None:
        merged["network"] = {**existing_network, **incoming_network}
    elif existing_network:
        merged["network"] = existing_network
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(merged, f, indent=2)


def load_secret_key() -> str:
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRET_FILE.write_text(key)
    os.chmod(SECRET_FILE, 0o600)
    return key


def verify_password(password: str) -> bool:
    if not AUTH_FILE.exists():
        return False
    with open(AUTH_FILE) as f:
        auth = json.load(f)
    stored = auth.get("password_hash", "").encode()
    return bcrypt.checkpw(password.encode(), stored)


def change_password(new_password: str):
    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUTH_FILE, "w") as f:
        json.dump({"password_hash": hashed}, f)
    os.chmod(AUTH_FILE, 0o600)

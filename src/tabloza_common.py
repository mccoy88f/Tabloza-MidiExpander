"""Tabloza MidiExpander — shared utilities."""

import json
import os
import secrets
from pathlib import Path

import bcrypt

HOSTNAME = "tabloza-me"
MDNS_NAME = f"{HOSTNAME}.local"

DATA_DIR = Path(os.environ.get("TABLOZA_DATA_DIR", "/var/lib/tabloza"))
CONFIG_FILE = DATA_DIR / "config.json"
AUTH_FILE = DATA_DIR / "auth.json"
SECRET_FILE = DATA_DIR / "secret.key"
SOUNDFONTS_DIR = DATA_DIR / "soundfonts"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"active_soundfont": "", "volume": 100}


def save_config(config: dict):
    existing = load_config() if CONFIG_FILE.exists() else {}
    merged = {**existing, **config}
    if "fluidsynth" in existing and "fluidsynth" not in config:
        merged["fluidsynth"] = existing["fluidsynth"]
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

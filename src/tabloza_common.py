"""Tabloza MidiExpander — shared utilities."""

import json
import os
from pathlib import Path

import bcrypt

DATA_DIR = Path(os.environ.get("TABLOZA_DATA_DIR", "/var/lib/tabloza"))
CONFIG_FILE = DATA_DIR / "config.json"
AUTH_FILE = DATA_DIR / "auth.json"
SOUNDFONTS_DIR = DATA_DIR / "soundfonts"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"active_soundfont": "", "volume": 100}


def save_config(config: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


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

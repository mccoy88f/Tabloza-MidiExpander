#!/usr/bin/env python3
"""Tabloza MidiExpander — Flask web API and dashboard."""

import os
import re
import signal
import subprocess
import sys
import time
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from activity_status import get_audio_activity, get_midi_activity  # noqa: E402
from midi_utils import get_midi_status, send_cc7, send_test_note  # noqa: E402
from tabloza_common import (  # noqa: E402
    AUTHOR,
    GITHUB_URL,
    MDNS_NAME,
    SOUNDFONTS_DIR,
    change_password,
    get_version,
    load_config,
    load_secret_key,
    save_config,
    verify_password,
)

app = Flask(__name__, static_folder="static")
app.secret_key = load_secret_key()
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9._\- ]+\.sf2$", re.IGNORECASE)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify({"error": "Non autenticato"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


# --- Auth ---

@app.route("/api/version")
def api_version():
    return jsonify({
        "version": get_version(),
        "github": GITHUB_URL,
        "author": AUTHOR,
    })


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if verify_password(password):
        session["authenticated"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "Password errata"}), 401


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.pop("authenticated", None)
    return jsonify({"ok": True})


@app.route("/api/auth/check", methods=["GET"])
def auth_check():
    return jsonify({"authenticated": session.get("authenticated", False)})


@app.route("/api/auth/change-password", methods=["POST"])
@require_auth
def api_change_password():
    data = request.get_json(silent=True) or {}
    current = data.get("current_password", "")
    new_pw = data.get("new_password", "")
    if not new_pw or len(new_pw) < 4:
        return jsonify({"error": "Nuova password troppo corta (min 4 caratteri)"}), 400
    if not verify_password(current):
        return jsonify({"error": "Password attuale errata"}), 401
    change_password(new_pw)
    return jsonify({"ok": True})


# --- Status ---

@app.route("/api/status")
@require_auth
def api_status():
    config = load_config()
    midi = get_midi_status()
    return jsonify({
        "ip": _get_ip(),
        "hostname": MDNS_NAME,
        "network_mode": _get_network_mode(),
        "midi": midi,
        "activity": {
            "midi": get_midi_activity(),
            "audio": get_audio_activity(),
        },
        "active_soundfont": config.get("active_soundfont", ""),
        "volume": config.get("volume", 100),
    })


# --- SoundFonts ---

@app.route("/api/soundfonts")
@require_auth
def api_soundfonts():
    config = load_config()
    active = config.get("active_soundfont", "")
    fonts = []
    SOUNDFONTS_DIR.mkdir(parents=True, exist_ok=True)
    for sf in sorted(SOUNDFONTS_DIR.glob("*.sf2")):
        fonts.append({
            "name": sf.name,
            "size": sf.stat().st_size,
            "active": sf.name == active,
        })
    return jsonify({"soundfonts": fonts, "active": active})


@app.route("/api/soundfonts/select", methods=["POST"])
@require_auth
def api_select_soundfont():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    path = SOUNDFONTS_DIR / name
    if not path.is_file():
        return jsonify({"error": "SoundFont non trovato"}), 404
    config = load_config()
    config["active_soundfont"] = name
    save_config(config)
    _reload_orchestrator()
    return jsonify({"ok": True, "active": name})


@app.route("/api/soundfonts/upload", methods=["POST"])
@require_auth
def api_upload_soundfont():
    if "file" not in request.files:
        return jsonify({"error": "Nessun file"}), 400
    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith(".sf2"):
        return jsonify({"error": "Solo file .sf2"}), 400
    safe_name = Path(f.filename).name
    if not SAFE_FILENAME.match(safe_name):
        return jsonify({"error": "Nome file non valido"}), 400
    SOUNDFONTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = SOUNDFONTS_DIR / safe_name
    f.save(dest)
    config = load_config()
    config["active_soundfont"] = safe_name
    save_config(config)
    _reload_orchestrator()
    return jsonify({"ok": True, "name": safe_name, "active": True})


@app.route("/api/soundfonts/<name>", methods=["DELETE"])
@require_auth
def api_delete_soundfont(name):
    if not SAFE_FILENAME.match(name):
        return jsonify({"error": "Nome non valido"}), 400
    path = SOUNDFONTS_DIR / name
    if not path.is_file():
        return jsonify({"error": "Non trovato"}), 404
    config = load_config()
    if config.get("active_soundfont") == name:
        config["active_soundfont"] = ""
        save_config(config)
        _reload_orchestrator()
    path.unlink()
    return jsonify({"ok": True})


# --- Volume ---

@app.route("/api/volume", methods=["POST"])
@require_auth
def api_volume():
    data = request.get_json(silent=True) or {}
    vol = data.get("volume")
    if vol is None or not (0 <= int(vol) <= 127):
        return jsonify({"error": "Volume deve essere 0-127"}), 400
    vol = int(vol)
    config = load_config()
    config["volume"] = vol
    save_config(config)
    send_cc7(vol)
    return jsonify({"ok": True, "volume": vol})


# --- WiFi ---

@app.route("/api/wifi/scan")
@require_auth
def api_wifi_scan():
    try:
        subprocess.run(["nmcli", "device", "wifi", "rescan"], timeout=10, check=False)
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return jsonify({"error": "Scan WiFi fallito"}), 500

    networks = []
    seen = set()
    for line in result.stdout.strip().splitlines():
        parts = line.split(":")
        if len(parts) < 2:
            continue
        ssid = parts[0]
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        networks.append({
            "ssid": ssid,
            "signal": int(parts[1]) if parts[1].isdigit() else 0,
            "security": parts[2] if len(parts) > 2 else "",
        })
    networks.sort(key=lambda n: n["signal"], reverse=True)
    return jsonify({"networks": networks})


@app.route("/api/wifi/connect", methods=["POST"])
@require_auth
def api_wifi_connect():
    data = request.get_json(silent=True) or {}
    ssid = data.get("ssid", "").strip()
    password = data.get("password", "")
    if not ssid:
        return jsonify({"error": "SSID richiesto"}), 400

    conn_name = f"tabloza-wifi-{ssid[:20]}"
    try:
        subprocess.run(
            ["nmcli", "connection", "delete", conn_name],
            capture_output=True, timeout=5, check=False,
        )
        cmd = [
            "nmcli", "connection", "add",
            "type", "wifi",
            "con-name", conn_name,
            "ssid", ssid,
            "wifi-sec.key-mgmt", "wpa-psk" if password else "none",
        ]
        if password:
            cmd += ["wifi-sec.psk", password]
        subprocess.run(cmd, capture_output=True, timeout=10, check=True)
        subprocess.run(
            ["nmcli", "connection", "up", conn_name],
            capture_output=True, timeout=30, check=True,
        )
        subprocess.run(
            ["nmcli", "connection", "down", "tabloza-hotspot"],
            capture_output=True, timeout=10, check=False,
        )
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or str(e))
        return jsonify({"error": f"Connessione fallita: {err}"}), 500

    return jsonify({"ok": True, "ssid": ssid})


# --- MIDI Reset ---

@app.route("/api/audio/test", methods=["POST"])
@require_auth
def api_audio_test():
    """Play a short test note directly on FluidSynth (bypasses RTP-MIDI)."""
    if not send_test_note():
        return jsonify({"error": "Impossibile inviare nota di test (FluidSynth non pronto)"}), 503
    return jsonify({"ok": True, "message": "Nota di test inviata"})


@app.route("/api/midi/reset", methods=["POST"])
@require_auth
def api_midi_reset():
    try:
        subprocess.run(
            ["systemctl", "restart", "rtpmidid"],
            capture_output=True, timeout=15, check=True,
        )
        subprocess.run(
            ["systemctl", "restart", "tabloza-orchestrator"],
            capture_output=True, timeout=15, check=True,
        )
        time.sleep(3)
        config = load_config()
        send_cc7(config.get("volume", 100))
        midi = get_midi_status()
        return jsonify({
            "ok": True,
            "message": "FluidSynth e routing MIDI riavviati",
            "midi": midi,
        })
    except subprocess.CalledProcessError:
        return jsonify({"error": "Reset MIDI fallito"}), 500


# --- Helpers ---

def _reload_orchestrator():
    try:
        result = subprocess.run(
            ["pgrep", "-f", "midi_orchestrator.py"],
            capture_output=True, text=True, timeout=5,
        )
        for pid in result.stdout.strip().split():
            os.kill(int(pid), signal.SIGHUP)
    except (ProcessLookupError, ValueError, subprocess.TimeoutExpired):
        subprocess.run(
            ["systemctl", "restart", "tabloza-orchestrator"],
            timeout=10, check=False,
        )


def _get_ip() -> str:
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip().split()[0] if result.stdout.strip() else "0.0.0.0"
    except (subprocess.TimeoutExpired, FileNotFoundError, IndexError):
        return "0.0.0.0"


def _get_network_mode() -> str:
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            name, ctype = line.split(":", 1)
            if ctype == "802-11-wireless":
                return "hotspot" if "hotspot" in name.lower() else "client"
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return "unknown"


if __name__ == "__main__":
    SOUNDFONTS_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("TABLOZA_WEB_PORT", "80"))
    app.run(host="0.0.0.0", port=port, debug=False)

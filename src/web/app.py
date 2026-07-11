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
from event_log import clear_events, log_event, read_events  # noqa: E402
import alsaaudio
from audio_utils import (  # noqa: E402
    apply_output_volume,
    card_from_audio_device,
    device_label,
    list_playback_devices,
    play_stereo_tone,
    probe_playback_device,
    resolve_audio_device,
    sample_rate_for_device,
)
from soundfont_config import resolve_default_soundfont, set_default_soundfont  # noqa: E402
from fluidsynth_client import read_soundfont_state  # noqa: E402
from midi_utils import (
    get_midi_status,
    trigger_orchestrator_apply_synth_settings,
    trigger_orchestrator_apply_volume,
    trigger_orchestrator_reload_fluidsynth,
    trigger_orchestrator_stop_notes,
    trigger_orchestrator_test_note,
    wait_fluidsynth_midi_ready,
)  # noqa: E402
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
from soundfont_config import (  # noqa: E402
    resolve_default_soundfont,
    set_default_soundfont,
    startup_soundfont_name,
)
from synth_config import parse_synth_settings_update, synth_settings_for_api  # noqa: E402
from system_stats import SF2_MAX_UPLOAD_BYTES, get_device_stats  # noqa: E402
from update_utils import apply_update_if_needed, check_for_update, read_update_status  # noqa: E402
from network_utils import start_lan_direct, stop_lan_direct  # noqa: E402
from wifi_utils import (  # noqa: E402
    connect_wifi_network,
    disable_wifi,
    enable_wifi,
    get_network_status,
    scan_wifi_networks,
    start_hotspot,
    stop_hotspot,
)

app = Flask(__name__, static_folder="static")
app.secret_key = load_secret_key()
app.config["MAX_CONTENT_LENGTH"] = SF2_MAX_UPLOAD_BYTES
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9._\- ]+\.sf2$", re.IGNORECASE)


@app.errorhandler(413)
def request_entity_too_large(_e):
    max_mb = SF2_MAX_UPLOAD_BYTES // (1024 * 1024)
    return jsonify({"error": f"File troppo grande (max {max_mb} MB)"}), 413


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

def _orchestrator_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "midi_orchestrator.py"],
            capture_output=True, text=True, timeout=3,
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@app.route("/api/status")
@require_auth
def api_status():
    config = load_config()
    midi = get_midi_status()
    sf_state = read_soundfont_state()
    audio = get_audio_activity()
    network = get_network_status()
    engine_running = bool(audio.get("fluidsynth_running"))
    midi_ready = midi.get("fluidsynth") is not None
    orchestrator_running = _orchestrator_running()
    starting = orchestrator_running and (not engine_running or not midi_ready)
    return jsonify({
        "ip": _get_ip(),
        "hostname": MDNS_NAME,
        "network": network,
        "network_mode": network["network_mode"],
        "midi": midi,
        "activity": {
            "midi": get_midi_activity(),
            "audio": audio,
        },
        "synth": {
            "engine_running": engine_running,
            "midi_ready": midi_ready,
            "starting": starting,
            "orchestrator_running": orchestrator_running,
        },
        "soundfont": {
            "selected": config.get("active_soundfont", ""),
            "loaded": sf_state.get("loaded", ""),
            "loading": sf_state.get("loading", False),
            "error": sf_state.get("error"),
        },
        "active_soundfont": config.get("active_soundfont", ""),
        "volume": config.get("volume", 100),
        "audio": {
            "device": resolve_audio_device(config.get("fluidsynth", {}).get("audio_device", "plughw:0,0")),
            "alsa_card": int(config.get("fluidsynth", {}).get("alsa_card", 0)),
        },
        "synth_settings": synth_settings_for_api(config),
        "version": get_version(),
    })


# --- System update ---

@app.route("/api/update/check")
@require_auth
def api_update_check():
    result = check_for_update(fetch=True)
    if not result.get("ok"):
        return jsonify(result), 503
    return jsonify(result)


@app.route("/api/update/apply", methods=["POST"])
@require_auth
def api_update_apply():
    log_event("web", "Verifica aggiornamenti software…")
    result = apply_update_if_needed()
    if result.get("busy"):
        return jsonify({"error": result["error"]}), 409
    if not result.get("ok"):
        log_event("web", f"Aggiornamento fallito: {result.get('error', '?')}", "error")
        return jsonify({"error": result.get("error", "Aggiornamento fallito")}), 500
    if result.get("applied"):
        log_event(
            "web",
            f"Aggiornato {result.get('previous_version', '?')} → {result.get('current_version', '?')}",
        )
    else:
        log_event("web", f"Nessun aggiornamento (v{result.get('current_version', '?')})")
    return jsonify(result)


@app.route("/api/update/status")
@require_auth
def api_update_status():
    status = read_update_status()
    status["version"] = get_version()
    return jsonify(status)


# --- Synth engine ---

@app.route("/api/synth/settings")
@require_auth
def api_synth_settings_get():
    return jsonify(synth_settings_for_api(load_config()))


@app.route("/api/synth/settings", methods=["POST"])
@require_auth
def api_synth_settings_post():
    data = request.get_json(silent=True) or {}
    config = load_config()
    try:
        fs_cfg, needs_restart = parse_synth_settings_update(data, config)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

    config["fluidsynth"] = fs_cfg
    save_config(config)
    log_event("web", f"Motore synth → preset {fs_cfg.get('audio_preset', 'standard')}")

    if needs_restart:
        if not trigger_orchestrator_reload_fluidsynth():
            return jsonify({"error": "Orchestrator non attivo"}), 503
        if not wait_fluidsynth_midi_ready(50.0):
            return jsonify({
                "error": "FluidSynth non ripartito — verifica log orchestrator",
            }), 503
    elif not trigger_orchestrator_apply_synth_settings():
        return jsonify({"error": "Impossibile applicare impostazioni synth"}), 503

    return jsonify({
        "ok": True,
        "restarted": needs_restart,
        "settings": synth_settings_for_api(config),
    })


@app.route("/api/synth/stop-notes", methods=["POST"])
@require_auth
def api_synth_stop_notes():
    if not trigger_orchestrator_stop_notes():
        return jsonify({"error": "Orchestrator non raggiungibile"}), 503
    log_event("web", "Stop note synth")
    return jsonify({"ok": True, "message": "Note silenziate"})


# --- SoundFonts ---

@app.route("/api/soundfonts")
@require_auth
def api_soundfonts():
    config = load_config()
    active = config.get("active_soundfont", "")
    default = resolve_default_soundfont(config)
    sf_state = read_soundfont_state()
    loaded = sf_state.get("loaded", "")
    loading = sf_state.get("loading", False)
    fonts = []
    SOUNDFONTS_DIR.mkdir(parents=True, exist_ok=True)
    for sf in sorted(SOUNDFONTS_DIR.glob("*.sf2")):
        fonts.append({
            "name": sf.name,
            "size": sf.stat().st_size,
            "selected": sf.name == active,
            "loaded": sf.name == loaded,
            "loading": loading and sf.name == active,
            "active": sf.name == active,
            "default": sf.name == default,
        })
    return jsonify({
        "soundfonts": fonts,
        "active": active,
        "default": default,
        "loaded": loaded,
        "loading": loading,
        "error": sf_state.get("error"),
    })


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


@app.route("/api/soundfonts/eject", methods=["POST"])
@require_auth
def api_eject_soundfont():
    config = load_config()
    sf_state = read_soundfont_state()
    loaded = sf_state.get("loaded", "")
    active = config.get("active_soundfont", "")
    if not loaded and not active and not sf_state.get("loading"):
        return jsonify({"error": "Nessun SoundFont da espellere"}), 400
    ejected = loaded or active
    config["active_soundfont"] = ""
    save_config(config)
    log_event("web", f"SoundFont espulso: {ejected or '—'}")
    _reload_orchestrator()
    return jsonify({"ok": True, "ejected": ejected})


@app.route("/api/soundfonts/default", methods=["POST", "DELETE"])
@require_auth
def api_default_soundfont():
    if request.method == "DELETE":
        config = load_config()
        previous = resolve_default_soundfont(config)
        config = set_default_soundfont(config, None)
        save_config(config)
        log_event("web", "SF2 predefinito rimosso")
        return jsonify({"ok": True, "default": "", "previous": previous})

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    path = SOUNDFONTS_DIR / name
    if not path.is_file():
        return jsonify({"error": "SoundFont non trovato"}), 404
    config = load_config()
    previous = resolve_default_soundfont(config)
    config = set_default_soundfont(config, name)
    save_config(config)
    if previous and previous != name:
        log_event("web", f"SF2 predefinito: {name} (sostituisce {previous})")
    else:
        log_event("web", f"SF2 predefinito: {name}")
    return jsonify({
        "ok": True,
        "default": name,
        "previous": previous if previous != name else "",
    })


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
    return jsonify({"ok": True, "name": safe_name, "message": "Carica il file dalla libreria SoundFont"})


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
    config = load_config()
    if config.get("default_soundfont") == name:
        save_config({"default_soundfont": ""})
    path.unlink()
    return jsonify({"ok": True})


# --- Volume ---

@app.route("/api/volume", methods=["POST"])
@require_auth
def api_volume():
    data = request.get_json(silent=True) or {}
    vol = data.get("volume")
    if vol is None or not (0 <= int(vol) <= 100):
        return jsonify({"error": "Volume deve essere 0-100%"}), 400
    vol = int(vol)
    config = load_config()
    config["volume"] = vol
    save_config(config)
    ok_alsa, alsa_detail = apply_output_volume(vol, config)
    if not trigger_orchestrator_apply_volume():
        return jsonify({"error": "Impossibile sincronizzare FluidSynth (orchestrator non attivo)"}), 503
    return jsonify({
        "ok": True,
        "volume": vol,
        "alsa": alsa_detail,
        "alsa_ok": ok_alsa,
    })


# --- Audio output ---

@app.route("/api/audio/devices")
@require_auth
def api_audio_devices():
    config = load_config()
    current = resolve_audio_device(config.get("fluidsynth", {}).get("audio_device", "plughw:0,0"))
    devices = list_playback_devices()
    current_label = device_label(current, devices)
    current_dev = next((d for d in devices if d["id"] == current), None)
    if current_dev and not current_dev.get("openable", True):
        current_label = f"{current_label} (non disponibile)"
    elif current and current not in {d["id"] for d in devices}:
        current_label = f"{current} (non rilevato)"
    return jsonify({
        "devices": devices,
        "current": current,
        "current_label": current_label,
    })


@app.route("/api/audio/select", methods=["POST"])
@require_auth
def api_audio_select():
    from audio_utils import AUDIO_DEVICE_ID_RE

    data = request.get_json(silent=True) or {}
    device = data.get("device", "").strip()
    if not AUDIO_DEVICE_ID_RE.match(device):
        return jsonify({"error": "Dispositivo non valido"}), 400

    devices = list_playback_devices()
    match = next((d for d in devices if d["id"] == device), None)
    if devices and not match:
        return jsonify({"error": "Dispositivo non trovato"}), 404
    openable, probe_err = probe_playback_device(device)

    config = load_config()
    card = card_from_audio_device(device)
    resolved = resolve_audio_device(device)
    config.setdefault("fluidsynth", {})["audio_device"] = resolved
    config["fluidsynth"]["alsa_card"] = card
    config["fluidsynth"]["sample_rate"] = sample_rate_for_device(resolved)
    save_config(config)
    log_event("web", f"Uscita audio → {resolved}")
    if not trigger_orchestrator_reload_fluidsynth():
        return jsonify({"error": "Orchestrator non attivo"}), 503
    if not wait_fluidsynth_midi_ready(50.0):
        return jsonify({
            "error": "FluidSynth non ripartito con la nuova uscita — verifica dispositivo e log (HDMI richiede plughw)",
        }), 503

    ok_alsa, alsa_detail = apply_output_volume(config.get("volume", 100), config)

    return jsonify({
        "ok": True,
        "device": resolved,
        "label": device_label(resolved, devices),
        "alsa_card": card,
        "alsa": alsa_detail,
        "alsa_ok": ok_alsa,
        "openable": openable,
        "probe_warning": None if openable else (probe_err or "dispositivo non verificato"),
        "startup_soundfont": startup_soundfont_name(config),
    })


# --- WiFi ---

@app.route("/api/wifi/scan")
@require_auth
def api_wifi_scan():
    try:
        networks, err = scan_wifi_networks()
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log_event("wifi", f"Scan WiFi eccezione: {exc}", "error")
        return jsonify({"error": "Scan WiFi fallito — nmcli non disponibile?"}), 500

    if err:
        return jsonify({"error": err, "networks": networks}), 500
    return jsonify({"networks": networks})


@app.route("/api/wifi/connect", methods=["POST"])
@require_auth
def api_wifi_connect():
    data = request.get_json(silent=True) or {}
    ssid = data.get("ssid", "").strip()
    password = data.get("password", "")
    security = data.get("security", "")
    if not ssid:
        return jsonify({"error": "SSID richiesto"}), 400

    ok, err = connect_wifi_network(ssid, password, security)
    if not ok:
        return jsonify({"error": f"Connessione fallita: {err}"}), 500

    return jsonify({"ok": True, "ssid": ssid})


@app.route("/api/wifi/hotspot/start", methods=["POST"])
@require_auth
def api_wifi_hotspot_start():
    ok, err = start_hotspot()
    if not ok:
        return jsonify({"error": err or "Hotspot fallito"}), 500
    return jsonify({"ok": True, **get_network_status()})


@app.route("/api/wifi/hotspot/stop", methods=["POST"])
@require_auth
def api_wifi_hotspot_stop():
    ok, err = stop_hotspot()
    if not ok:
        return jsonify({"error": err or "Spegnimento hotspot fallito"}), 500
    return jsonify({"ok": True, **get_network_status()})


@app.route("/api/wifi/disable", methods=["POST"])
@require_auth
def api_wifi_disable():
    ok, err = disable_wifi()
    if not ok:
        return jsonify({"error": err or "Disattivazione WiFi fallita"}), 500
    return jsonify({"ok": True, **get_network_status()})


@app.route("/api/wifi/enable", methods=["POST"])
@require_auth
def api_wifi_enable():
    ok, err = enable_wifi()
    if not ok:
        return jsonify({"error": err or "Attivazione WiFi fallita"}), 500
    return jsonify({"ok": True, **get_network_status()})


@app.route("/api/device/reboot", methods=["POST"])
@require_auth
def api_device_reboot():
    log_event("system", "Riavvio dispositivo richiesto dal pannello web")
    try:
        subprocess.Popen(
            ["/sbin/reboot"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return jsonify({"error": f"Riavvio fallito: {exc}"}), 500
    return jsonify({"ok": True, "message": "Riavvio in corso…"})


@app.route("/api/network/lan-direct/start", methods=["POST"])
@require_auth
def api_lan_direct_start():
    ok, err = start_lan_direct()
    if not ok:
        return jsonify({"error": err or "Link LAN diretto fallito"}), 500
    return jsonify({"ok": True, **get_network_status()})


@app.route("/api/network/lan-direct/stop", methods=["POST"])
@require_auth
def api_lan_direct_stop():
    ok, err = stop_lan_direct()
    if not ok:
        return jsonify({"error": err or "Spegnimento link LAN fallito"}), 500
    return jsonify({"ok": True, **get_network_status()})


# --- Device stats ---

@app.route("/api/device/stats")
@require_auth
def api_device_stats():
    return jsonify(get_device_stats(SOUNDFONTS_DIR))


# --- Console ---

@app.route("/api/console")
@require_auth
def api_console():
    return jsonify({"lines": read_events(200)})


@app.route("/api/console/clear", methods=["POST"])
@require_auth
def api_console_clear():
    clear_events()
    log_event("web", "Console svuotata")
    return jsonify({"ok": True})


# --- MIDI Reset ---

@app.route("/api/audio/test", methods=["POST"])
@require_auth
def api_audio_test():
    """Play a short test note via orchestrator (shell FluidSynth bound there only)."""
    sf_state = read_soundfont_state()
    loaded = sf_state.get("loaded", "")
    if not loaded:
        config = load_config()
        selected = config.get("active_soundfont", "")
        if selected and sf_state.get("loading"):
            return jsonify({"error": "SoundFont in caricamento — attendi qualche secondo"}), 503
        if not selected:
            return jsonify({
                "error": "Nessun SoundFont caricato — seleziona un file e premi Carica",
            }), 400
        return jsonify({
            "error": f"SoundFont {selected} selezionato ma non caricato — premi Carica",
        }), 400
    midi = get_midi_status()
    if not midi.get("fluidsynth"):
        return jsonify({"error": "FluidSynth non pronto — attendi qualche secondo"}), 503
    if not trigger_orchestrator_test_note():
        return jsonify({"error": "Orchestrator non raggiungibile"}), 503
    return jsonify({
        "ok": True,
        "message": "Nota di test inviata",
        "port": midi["fluidsynth"]["address"],
    })


@app.route("/api/audio/test-hardware", methods=["POST"])
@require_auth
def api_audio_test_hardware():
    """Play a sine tone directly on the configured ALSA output (bypasses FluidSynth/MIDI)."""
    cfg = load_config().get("fluidsynth", {})
    device = resolve_audio_device(cfg.get("audio_device", "plughw:0,0"))
    rate = int(cfg.get("sample_rate", sample_rate_for_device(device)))
    label = device_label(device)
    try:
        play_stereo_tone(device, sample_rate=rate)
        return jsonify({
            "ok": True,
            "message": f"Segnale stereo 440 Hz inviato a {label}",
            "device": device,
            "label": label,
        })
    except alsaaudio.ALSAAudioError as exc:
        err = str(exc).lower()
        if "busy" in err and trigger_orchestrator_test_note():
            return jsonify({
                "ok": True,
                "message": (
                    f"Uscita {label} in uso da FluidSynth — inviata nota di test MIDI"
                ),
                "device": device,
                "label": label,
                "via": "fluidsynth",
            })
        return jsonify({"error": f"Test audio fallito su {label}: {exc}"}), 500
    except OSError as exc:
        return jsonify({"error": f"Test audio fallito: {exc}"}), 500


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
        trigger_orchestrator_apply_volume()
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


if __name__ == "__main__":
    SOUNDFONTS_DIR.mkdir(parents=True, exist_ok=True)
    log_event("web", "Pannello web avviato")
    port = int(os.environ.get("TABLOZA_WEB_PORT", "80"))
    app.run(host="0.0.0.0", port=port, debug=False)

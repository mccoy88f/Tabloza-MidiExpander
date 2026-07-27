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
    current_audio_device_id,
    device_label,
    list_all_playback_devices,
    list_playback_devices,
    play_stereo_tone,
    resolve_audio_device,
    sample_rate_for_device,
)
from soundfont_config import resolve_default_soundfont, set_default_soundfont  # noqa: E402
from fluidsynth_client import read_soundfont_state, request_cancel_soundfont_load  # noqa: E402
from midi_utils import (
    get_midi_status,
    get_midi_settings_for_api,
    read_synth_effects_runtime,
    trigger_orchestrator_apply_midi_settings,
    trigger_orchestrator_apply_synth_settings,
    trigger_orchestrator_apply_volume,
    trigger_orchestrator_query_synth_effects,
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
from midi_config import parse_midi_settings_update  # noqa: E402
from rtpmidid_config import apply_rtpmidid_config  # noqa: E402
from synth_config import merge_fluidsynth_config, normalize_synth_gain, parse_synth_settings_update, synth_settings_for_api  # noqa: E402
from system_stats import SF2_MAX_UPLOAD_BYTES, get_device_stats  # noqa: E402
from update_utils import apply_update_if_needed, check_for_update, read_update_status  # noqa: E402
from network_utils import start_lan_direct, stop_lan_direct  # noqa: E402
from wifi_utils import (  # noqa: E402
    connect_wifi_network,
    delete_saved_wifi_network,
    disable_wifi,
    enable_wifi,
    get_network_status,
    list_saved_wifi_networks,
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


@app.after_request
def _disable_api_cache(response):
    """Evita 301 HTTP→HTTPS in cache (v2.3) su /api/* e sulla shell HTML."""
    if request.path.startswith("/api/") or request.path in ("/", "/kiosk", "/setup/sing"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.errorhandler(413)
def request_entity_too_large(_e):
    max_mb = SF2_MAX_UPLOAD_BYTES // (1024 * 1024)
    return jsonify({"error": f"File troppo grande (max {max_mb} MB)"}), 413


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Auto-autentica se la richiesta proviene da localhost (kiosk Pi) o sessione kiosk
        if request.remote_addr in ("127.0.0.1", "::1") or session.get("kiosk"):
            session["authenticated"] = True
        if not session.get("authenticated"):
            return jsonify({"error": "Non autenticato"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/kiosk")
def kiosk():
    """Interfaccia Touch Kiosk per display DSI 4.3" / schermi locali e mobile."""
    session["authenticated"] = True
    session["kiosk"] = True
    return send_from_directory(app.static_folder, "kiosk.html")


@app.route("/setup/sing")
def setup_sing():
    """Pagina pubblica per verificare il WebSocket MIDI (Tabloza Sing)."""
    return send_from_directory(app.static_folder, "setup-sing.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


# --- Auth ---

@app.route("/api/version")
def api_version():
    ws_port = int(os.environ.get("TABLOZA_MIDI_WS_PORT", "8765"))
    return jsonify({
        "version": get_version(),
        "github": GITHUB_URL,
        "author": AUTHOR,
        "midi_ws": {
            "scheme": "wss",
            "port": ws_port,
            "setup_url": f"https://{MDNS_NAME}:{ws_port}/setup",
        },
    })


@app.route("/api/tls/certificate")
def api_tls_certificate():
    """Certificato pubblico (auto-firmato) da installare sul PC del display."""
    try:
        from tls_utils import read_certificate_pem
        pem = read_certificate_pem()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503
    return (
        pem,
        200,
        {
            "Content-Type": "application/x-pem-file",
            "Content-Disposition": 'attachment; filename="tabloza-me.pem"',
        },
    )


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
            "load_progress": sf_state.get("load_progress"),
        },
        "active_soundfont": config.get("active_soundfont", ""),
        "volume": config.get("volume", 100),
        "synth_gain": merge_fluidsynth_config(config.get("fluidsynth")).get("gain", 2.0),
        "audio": {
            "device": current_audio_device_id(config.get("fluidsynth")),
            "driver": (config.get("fluidsynth") or {}).get("audio_driver", "alsa"),
            "alsa_card": int(config.get("fluidsynth", {}).get("alsa_card", 0)),
        },
        "synth_settings": synth_settings_for_api(config),
        "midi_settings": get_midi_settings_for_api(config),
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


@app.route("/api/device/stats")
@require_auth
def api_device_stats():
    return jsonify(get_device_stats(SOUNDFONTS_DIR))


# --- Synth engine ---

@app.route("/api/synth/settings")
@require_auth
def api_synth_settings_get():
    return jsonify(synth_settings_for_api(load_config()))


def _fluidsynth_package_info() -> dict:
    info = {"binary": "/usr/bin/fluidsynth"}
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", "fluidsynth"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            info["package_version"] = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    try:
        result = subprocess.run(
            ["/usr/bin/fluidsynth", "-V"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        for line in (result.stdout or result.stderr or "").splitlines():
            if "FluidSynth runtime version" in line:
                info["runtime_version"] = line.split("version", 1)[-1].strip()
                break
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return info


@app.route("/api/synth/effects")
@require_auth
def api_synth_effects():
    runtime = read_synth_effects_runtime(max_age_sec=0)
    if runtime is None:
        if not trigger_orchestrator_query_synth_effects():
            return jsonify({"error": "Orchestrator non attivo"}), 503
        runtime = None
        for _ in range(20):
            time.sleep(0.15)
            runtime = read_synth_effects_runtime(max_age_sec=5.0)
            if runtime:
                break
        if runtime is None:
            return jsonify({"error": "Timeout lettura effetti FluidSynth"}), 504

    config = synth_settings_for_api(load_config())
    return jsonify({
        "ok": True,
        "tabloza": {
            "reverb": config.get("reverb"),
            "chorus": config.get("chorus"),
        },
        "fluidsynth": _fluidsynth_package_info(),
        "runtime_effects": runtime.get("effects", {}),
        "queried_at": runtime.get("queried_at"),
    })


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
    save_config({"fluidsynth": fs_cfg})
    log_event("web", f"Motore synth → preset {fs_cfg.get('audio_preset', 'stable')}")

    if needs_restart:
        if not trigger_orchestrator_reload_fluidsynth():
            return jsonify({"error": "Orchestrator non attivo"}), 503
        if not wait_fluidsynth_midi_ready(50.0):
            return jsonify({
                "error": "FluidSynth non ripartito — verifica log orchestrator",
            }), 503
        _reload_orchestrator()
    elif not trigger_orchestrator_apply_synth_settings():
        return jsonify({"error": "Impossibile applicare impostazioni synth"}), 503

    return jsonify({
        "ok": True,
        "restarted": needs_restart,
        "settings": synth_settings_for_api(config),
    })


@app.route("/api/midi/settings")
@require_auth
def api_midi_settings_get():
    return jsonify(get_midi_settings_for_api(load_config()))


@app.route("/api/midi/settings", methods=["POST"])
@require_auth
def api_midi_settings_post():
    data = request.get_json(silent=True) or {}
    config = load_config()
    try:
        midi_cfg, needs_restart, needs_buffer, needs_rtpmidid = parse_midi_settings_update(data, config)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

    config["midi"] = midi_cfg
    save_config({"midi": midi_cfg})
    log_event(
        "web",
        f"MIDI → bank {midi_cfg.get('bank_select', 'gs')}, "
        f"buffer RTP {'on' if midi_cfg.get('jitter_buffer_enabled') else 'off'}, "
        f"RTP ts {'on' if midi_cfg.get('rtp_midi_timestamps_enabled') else 'off'}, "
        f"SysEx auto {'on' if midi_cfg.get('sysex_bank_auto') else 'off'}",
    )

    rtpmidid_restarted = False
    if needs_rtpmidid:
        if not apply_rtpmidid_config(config):
            return jsonify({"error": "Impossibile riavviare rtpmidid"}), 503
        rtpmidid_restarted = True

    if needs_restart:
        if not trigger_orchestrator_reload_fluidsynth():
            return jsonify({"error": "Orchestrator non attivo"}), 503
        if not wait_fluidsynth_midi_ready(50.0):
            return jsonify({
                "error": "FluidSynth non ripartito — verifica log orchestrator",
            }), 503
        _reload_orchestrator()
    elif needs_buffer:
        if not trigger_orchestrator_apply_midi_settings():
            return jsonify({"error": "Impossibile applicare impostazioni MIDI"}), 503

    return jsonify({
        "ok": True,
        "restarted": needs_restart,
        "rtpmidid_restarted": rtpmidid_restarted,
        "settings": get_midi_settings_for_api(config),
    })


@app.route("/api/synth/stop-notes", methods=["POST"])
@require_auth
def api_synth_stop_notes():
    if not trigger_orchestrator_stop_notes():
        return jsonify({"error": "Orchestrator non raggiungibile"}), 503
    log_event("web", "Stop note synth")
    return jsonify({"ok": True, "message": "Note silenziate"})


@app.route("/api/synth/restart-software", methods=["POST"])
@require_auth
def api_synth_restart_software():
    log_event("web", "Riavvio software synth (orchestrator & FluidSynth)...")
    if not trigger_orchestrator_reload_fluidsynth():
        return jsonify({"error": "Orchestrator non raggiungibile"}), 503
    return jsonify({"ok": True, "message": "Software synth riavviato"})


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
        "load_progress": sf_state.get("load_progress"),
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
    loading = bool(sf_state.get("loading"))
    if not loaded and not active and not loading:
        return jsonify({"error": "Nessun SoundFont da espellere"}), 400
    ejected = loaded or active or sf_state.get("selected", "")
    if loading:
        request_cancel_soundfont_load()
    config["active_soundfont"] = ""
    save_config(config)
    log_event(
        "web",
        f"SoundFont espulso: {ejected or '—'}" + (" (caricamento interrotto)" if loading else ""),
    )
    _reload_orchestrator()
    return jsonify({
        "ok": True,
        "ejected": ejected,
        "cancelled_load": loading,
    })


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


@app.route("/api/synth-gain", methods=["POST"])
@require_auth
def api_synth_gain():
    data = request.get_json(silent=True) or {}
    if "gain" not in data:
        return jsonify({"error": "Parametro gain mancante"}), 400
    gain = normalize_synth_gain(data["gain"])
    config = load_config()
    fs = merge_fluidsynth_config(config.get("fluidsynth"))
    fs["gain"] = gain
    save_config({"fluidsynth": fs})
    if not trigger_orchestrator_apply_volume():
        return jsonify({"error": "Impossibile applicare guadagno synth (orchestrator non attivo)"}), 503
    log_event("web", f"Guadagno SoundFont → {gain:.2f}")
    return jsonify({"ok": True, "gain": gain})


# --- Audio output ---

@app.route("/api/audio/devices")
@require_auth
def api_audio_devices():
    config = load_config()
    fs = config.get("fluidsynth", {})
    current = current_audio_device_id(fs)
    devices = list_all_playback_devices()
    current_label = device_label(current, devices)
    if current and current not in {d["id"] for d in devices}:
        current_label = f"{current} (non rilevato)"
    from bluetooth_audio import pulse_available
    return jsonify({
        "devices": devices,
        "current": current,
        "current_label": current_label,
        "bluetooth_available": pulse_available(),
        "driver": (fs.get("audio_driver") or "alsa"),
    })


@app.route("/api/audio/select", methods=["POST"])
@require_auth
def api_audio_select():
    from audio_utils import AUDIO_DEVICE_ID_RE
    from bluetooth_audio import (
        ensure_pulse_sink_ready,
        is_pulse_device_id,
        pulse_device_id,
        pulse_sink_from_device_id,
    )

    data = request.get_json(silent=True) or {}
    device = data.get("device", "").strip()
    if not device:
        return jsonify({"error": "Dispositivo non valido"}), 400

    devices = list_all_playback_devices()
    match = next((d for d in devices if d["id"] == device), None)
    if devices and not match:
        return jsonify({"error": "Dispositivo non trovato — aggiorna l'elenco"}), 404

    config = load_config()
    config.setdefault("fluidsynth", {})

    if is_pulse_device_id(device):
        sink = pulse_sink_from_device_id(device)
        ok_bt, bt_detail = ensure_pulse_sink_ready(sink)
        if not ok_bt:
            return jsonify({"error": bt_detail}), 400
        config["fluidsynth"]["audio_driver"] = "pulse"
        config["fluidsynth"]["audio_device"] = pulse_device_id(sink)
        config["fluidsynth"]["sample_rate"] = 44100
        resolved = pulse_device_id(sink)
        card = int(config["fluidsynth"].get("alsa_card", 0))
    else:
        if not AUDIO_DEVICE_ID_RE.match(device):
            return jsonify({"error": "Dispositivo non valido"}), 400
        card = card_from_audio_device(device)
        resolved = resolve_audio_device(device)
        config["fluidsynth"]["audio_driver"] = "alsa"
        config["fluidsynth"]["audio_device"] = resolved
        config["fluidsynth"]["alsa_card"] = card
        config["fluidsynth"]["sample_rate"] = sample_rate_for_device(resolved)

    from synth_config import merge_fluidsynth_config
    save_config({"fluidsynth": merge_fluidsynth_config(config.get("fluidsynth"))})
    config = load_config()
    log_event("web", f"Uscita audio → {resolved}")
    if not trigger_orchestrator_reload_fluidsynth():
        return jsonify({"error": "Orchestrator non attivo"}), 503
    if not wait_fluidsynth_midi_ready(50.0):
        return jsonify({
            "error": (
                "FluidSynth non ripartito con la nuova uscita — "
                "per Bluetooth verifica pairing e profilo A2DP; per HDMI usa plughw"
            ),
        }), 503

    ok_vol, vol_detail = apply_output_volume(config.get("volume", 100), config)

    return jsonify({
        "ok": True,
        "device": resolved,
        "label": device_label(resolved, devices),
        "driver": config.get("fluidsynth", {}).get("audio_driver", "alsa"),
        "alsa_card": card,
        "alsa": vol_detail,
        "alsa_ok": ok_vol,
        "startup_soundfont": startup_soundfont_name(config),
    })


# --- Bluetooth pairing (Pi Lite / headless) ---

@app.route("/api/bluetooth/status")
@require_auth
def api_bluetooth_status():
    from bluetooth_audio import bluetooth_status
    return jsonify(bluetooth_status())


@app.route("/api/bluetooth/scan", methods=["POST"])
@require_auth
def api_bluetooth_scan():
    from bluetooth_audio import scan_bluetooth_devices
    data = request.get_json(silent=True) or {}
    duration = data.get("duration_sec")
    try:
        devices, err = scan_bluetooth_devices(duration)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        log_event("bluetooth", f"Scan fallito: {exc}", "error")
        return jsonify({"error": f"Scansione Bluetooth fallita: {exc}"}), 500
    if err:
        return jsonify({"error": err, "devices": devices}), 500
    log_event("bluetooth", f"Scansione: {len(devices)} dispositivi")
    return jsonify({"ok": True, "devices": devices})


@app.route("/api/bluetooth/pair", methods=["POST"])
@require_auth
def api_bluetooth_pair():
    from bluetooth_audio import pair_bluetooth_device
    data = request.get_json(silent=True) or {}
    address = (data.get("address") or "").strip()
    if not address:
        return jsonify({"error": "Indirizzo Bluetooth richiesto"}), 400
    ok, detail = pair_bluetooth_device(address)
    if not ok:
        log_event("bluetooth", f"Pair fallito {address}: {detail}", "error")
        return jsonify({"error": detail}), 400
    log_event("bluetooth", detail)
    from bluetooth_audio import list_bluetooth_sinks
    return jsonify({
        "ok": True,
        "message": detail,
        "sinks": list_bluetooth_sinks(),
    })


@app.route("/api/bluetooth/connect", methods=["POST"])
@require_auth
def api_bluetooth_connect():
    from bluetooth_audio import connect_bluetooth_device, list_bluetooth_sinks
    data = request.get_json(silent=True) or {}
    address = (data.get("address") or "").strip()
    if not address:
        return jsonify({"error": "Indirizzo Bluetooth richiesto"}), 400
    ok, detail = connect_bluetooth_device(address)
    if not ok:
        return jsonify({"error": detail}), 400
    log_event("bluetooth", detail)
    return jsonify({"ok": True, "message": detail, "sinks": list_bluetooth_sinks()})


@app.route("/api/bluetooth/disconnect", methods=["POST"])
@require_auth
def api_bluetooth_disconnect():
    from bluetooth_audio import disconnect_bluetooth_device
    data = request.get_json(silent=True) or {}
    address = (data.get("address") or "").strip()
    if not address:
        return jsonify({"error": "Indirizzo Bluetooth richiesto"}), 400
    ok, detail = disconnect_bluetooth_device(address)
    if not ok:
        return jsonify({"error": detail}), 400
    log_event("bluetooth", detail)
    return jsonify({"ok": True, "message": detail})


@app.route("/api/bluetooth/remove", methods=["POST"])
@require_auth
def api_bluetooth_remove():
    from bluetooth_audio import remove_bluetooth_device
    data = request.get_json(silent=True) or {}
    address = (data.get("address") or "").strip()
    if not address:
        return jsonify({"error": "Indirizzo Bluetooth richiesto"}), 400
    ok, detail = remove_bluetooth_device(address)
    if not ok:
        return jsonify({"error": detail}), 400
    log_event("bluetooth", detail)
    return jsonify({"ok": True, "message": detail})


# --- WiFi ---

@app.route("/api/wifi/saved")
@require_auth
def api_wifi_saved():
    saved = list_saved_wifi_networks()
    return jsonify({"saved": saved})


@app.route("/api/wifi/saved/delete", methods=["POST"])
@require_auth
def api_wifi_saved_delete():
    data = request.get_json(silent=True) or {}
    ssid = (data.get("ssid") or data.get("name") or "").strip()
    if not ssid:
        return jsonify({"error": "SSID o nome profilo richiesto"}), 400
    ok, err = delete_saved_wifi_network(ssid)
    if not ok:
        return jsonify({"error": err or "Eliminazione fallita"}), 500
    return jsonify({"ok": True, "saved": list_saved_wifi_networks()})


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


@app.route("/api/device/shutdown", methods=["POST"])
@require_auth
def api_device_shutdown():
    log_event("system", "Spegnimento dispositivo richiesto dal pannello web")
    try:
        subprocess.Popen(
            ["/sbin/shutdown", "-h", "now"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return jsonify({"error": f"Spegnimento fallito: {exc}"}), 500
    return jsonify({"ok": True, "message": "Spegnimento in corso…"})


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
    """Play a sine tone on ALSA output, or a MIDI test note when on Bluetooth."""
    config = load_config()
    cfg = config.get("fluidsynth", {})
    from bluetooth_audio import is_pulse_device_id

    device_id = current_audio_device_id(cfg)
    label = device_label(device_id, list_all_playback_devices())

    if is_pulse_device_id(device_id) or (cfg.get("audio_driver") or "").lower() == "pulse":
        if not trigger_orchestrator_test_note():
            return jsonify({
                "error": (
                    "Uscita Bluetooth attiva — impossibile il tono ALSA diretto; "
                    "anche la nota MIDI di test non è partita"
                ),
            }), 503
        return jsonify({
            "ok": True,
            "message": (
                f"Uscita Bluetooth ({label}): inviata nota di test via FluidSynth "
                "(tono hardware ALSA non disponibile su A2DP)"
            ),
            "device": device_id,
            "label": label,
            "via": "fluidsynth",
        })

    device = resolve_audio_device(cfg.get("audio_device", "plughw:0,0"))
    rate = int(cfg.get("sample_rate", sample_rate_for_device(device)))
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
        # Ripristina volume uscita salvato (BT/Pulse spesso torna al default dopo restart).
        config = load_config()
        vol = config.get("volume", 100)
        ok_vol, vol_detail = apply_output_volume(vol, config)
        if not ok_vol:
            log_event("web", f"Volume dopo MIDI reset non applicato: {vol_detail}", "error")
        trigger_orchestrator_apply_volume()
        midi = get_midi_status()
        return jsonify({
            "ok": True,
            "message": "FluidSynth e routing MIDI riavviati",
            "volume": vol,
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


def _start_https_to_http_redirect(https_port: int, http_port: int) -> None:
    """Intercetta browser con HSTS/HTTPS-first (es. dopo v2.3) e reindirizza a HTTP."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from tls_utils import load_ssl_context

    ssl_context = load_ssl_context()

    class _RedirectHandler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def _redirect(self) -> None:
            host = (self.headers.get("Host") or MDNS_NAME).split(":")[0]
            port_suffix = "" if http_port == 80 else f":{http_port}"
            location = f"http://{host}{port_suffix}{self.path}"
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def do_GET(self):
            self._redirect()

        def do_HEAD(self):
            self._redirect()

        def do_POST(self):
            self._redirect()

        def do_OPTIONS(self):
            self._redirect()

    def _serve() -> None:
        try:
            server = HTTPServer(("0.0.0.0", https_port), _RedirectHandler)
            server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
            server.serve_forever()
        except OSError as exc:
            log_event("web", f"Redirect HTTPS:{https_port}→HTTP:{http_port} non avviato ({exc})")

    threading.Thread(
        target=_serve,
        daemon=True,
        name="tabloza-https-redirect",
    ).start()
    log_event("web", f"Redirect HTTPS :{https_port} → HTTP :{http_port} (HSTS legacy)")


if __name__ == "__main__":
    SOUNDFONTS_DIR.mkdir(parents=True, exist_ok=True)
    log_event("web", "Pannello web avviato")
    port = int(os.environ.get("TABLOZA_WEB_PORT", "80"))
    https_redirect_port = int(os.environ.get("TABLOZA_WEB_HTTPS_REDIRECT_PORT", "443"))
    if port == 80 and https_redirect_port != port:
        _start_https_to_http_redirect(https_redirect_port, port)
    app.run(host="0.0.0.0", port=port, debug=False)

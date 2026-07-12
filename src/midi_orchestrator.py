#!/usr/bin/env python3
"""Tabloza MidiExpander — MIDI/Audio orchestrator.

Avvia FluidSynth senza SoundFont; il caricamento SF2 avviene su richiesta (UI / SIGHUP).

GPIO UART MIDI: planned — see docs/TODO.md
USB MIDI dongle: auto-routed in parallel with rtpmidid
"""

import json
import logging
import os
import shlex
import signal
import subprocess
import threading
import time
from pathlib import Path

from activity_status import touch_midi_activity, is_aseqdump_midi_event
from fluidsynth_client import (
    apply_runtime_synth_settings,
    bind_shell,
    cancel_soundfont_load_requested,
    clear_cancel_soundfont_load,
    clear_soundfont_state,
    load_soundfont,
    load_timeout_for,
    read_soundfont_state,
    reset_synth,
    shell_bound,
    unload_all_soundfonts,
    verify_soundfont_loaded,
    write_soundfont_state,
)
from midi_utils import (
    find_fluidsynth_input,
    get_active_routes,
    find_aseqdump_input,
    midi_monitor_command,
    refresh_midi_monitor_tap,
    refresh_midi_routes,
    route_rtpmidi_to_fluidsynth,
    send_test_note,
    set_fluidsynth_output_level,
    set_midi_monitor_input,
)

from event_log import log_event
from midi_config import (
    get_jitter_buffer_ms,
    get_midi_bank_select,
    get_ws_jitter_buffer_ms,
    is_sysex_bank_auto_enabled,
    is_ws_jitter_buffer_enabled,
    merge_midi_config,
)
from midi_jitter_buffer import (
    ensure_midi_gateway,
    reconnect_jitter_buffer_output,
    stop_jitter_buffer,
)
from midi_ws_buffer import ensure_ws_midi_gateway, stop_ws_midi_gateway
from midi_sysex_mode import reset_runtime_bank_select
from soundfont_config import startup_soundfont_name
from synth_config import merge_fluidsynth_config, fluidsynth_startup_options

DATA_DIR = Path(os.environ.get("TABLOZA_DATA_DIR", "/var/lib/tabloza"))
CONFIG_FILE = DATA_DIR / "config.json"
SOUNDFONTS_DIR = DATA_DIR / "soundfonts"

FLUIDSYNTH_BIN = "/usr/bin/fluidsynth"
FLUIDSYNTH_LOG = Path("/run/tabloza/fluidsynth.log")
RELOAD_FLUIDSYNTH_FLAG = Path("/run/tabloza/reload_fluidsynth")
APPLY_SYNTH_SETTINGS_FLAG = Path("/run/tabloza/apply_synth_settings")
STOP_SYNTH_NOTES_FLAG = Path("/run/tabloza/synth_stop_notes")
FLUID_STARTUP_TIMEOUT = 35.0
FLUID_RESTART_BACKOFF_SEC = 20.0
ROUTING_INTERVAL = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [orchestrator] %(levelname)s: %(message)s",
)
log = logging.getLogger("tabloza.orchestrator")

fluidsynth_proc: subprocess.Popen | None = None
fluidsynth_log_fd = None
shutdown = False
reload_fluidsynth_pending = False
fluidsynth_restart_after = 0.0
midi_monitor_proc: subprocess.Popen | None = None
midi_monitor_thread: threading.Thread | None = None
midi_monitor_stop = threading.Event()
soundfont_load_lock = threading.Lock()


def _apply_midi_jitter_buffer(config: dict | None = None) -> bool:
    cfg = config or load_config()
    reset_runtime_bank_select(get_midi_bank_select(cfg))
    ok = ensure_midi_gateway(
        get_jitter_buffer_ms(cfg),
        sysex_auto=is_sysex_bank_auto_enabled(cfg),
    )
    if ok:
        from midi_jitter_buffer import jitter_buffer_status

        st = jitter_buffer_status()
        log.info(
            "Gateway MIDI attivo (buffer=%sms, sysex=%s, porta=%s)",
            st.get("buffer_ms", 0),
            st.get("sysex_auto"),
            (st.get("input_port") or {}).get("address", "—"),
        )
    else:
        from rtmidi_compat import rtmidi_diagnostic

        log.error("Gateway MIDI non attivo — %s", rtmidi_diagnostic())
    return ok


def _apply_ws_midi_gateway(config: dict | None = None) -> bool:
    cfg = config or load_config()
    if not is_ws_jitter_buffer_enabled(cfg):
        stop_ws_midi_gateway()
        return False
    ok = ensure_ws_midi_gateway(
        get_ws_jitter_buffer_ms(cfg),
        sysex_auto=is_sysex_bank_auto_enabled(cfg),
    )
    if not ok:
        log.warning("Gateway WS Sing non attivo")
    return ok


def load_config() -> dict:
    defaults = {
        "active_soundfont": "",
        "default_soundfont": "",
        "volume": 100,
        "fluidsynth": merge_fluidsynth_config({}),
    }
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            stored = json.load(f)
        defaults.update(stored)
        defaults["fluidsynth"] = merge_fluidsynth_config(stored.get("fluidsynth"))
        defaults["midi"] = merge_midi_config(stored.get("midi"))
        if "volume" in defaults:
            from audio_utils import normalize_volume
            defaults["volume"] = normalize_volume(defaults["volume"])
    return defaults


def build_fluidsynth_cmd(config: dict) -> list[str]:
    """FluidSynth senza SF2 — caricamento dinamico via shell."""
    fs_cfg = merge_fluidsynth_config(config.get("fluidsynth"))
    max_gain = fs_cfg.get("gain", 2.0)
    from audio_utils import normalize_volume, resolve_audio_device
    from midi_utils import volume_to_gain

    vol = normalize_volume(config.get("volume", 100))
    initial_gain = volume_to_gain(vol, max_gain)
    audio_dev = resolve_audio_device(fs_cfg.get("audio_device", "plughw:0,0"))
    cmd = [
        FLUIDSYNTH_BIN,
        "-a", fs_cfg.get("audio_driver", "alsa"),
        "-o", f"audio.alsa.device={audio_dev}",
        "-r", str(fs_cfg.get("sample_rate", 44100)),
        "-z", str(fs_cfg.get("period_size", 512)),
        "-c", str(fs_cfg.get("period_count", 6)),
        "-g", str(initial_gain),
        "-m", "alsa_seq",
        "-o", "midi.autoconnect=false",
        "-o", "synth.default-soundfont=",
        "-o", f"synth.midi-bank-select={get_midi_bank_select(config)}",
    ]
    if is_sysex_bank_auto_enabled(config):
        cmd.extend(["-o", "synth.device-id=127"])
    for opt in fluidsynth_startup_options(fs_cfg):
        cmd.extend(["-o", opt])
    return cmd


def _ensure_alsa_seq():
    try:
        subprocess.run(["modprobe", "snd-seq"], capture_output=True, timeout=5, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def _launch_fluidsynth(cmd: list[str]) -> subprocess.Popen:
    global fluidsynth_log_fd
    FLUIDSYNTH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(FLUIDSYNTH_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n--- avvio {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        f.write(" ".join(shlex.quote(part) for part in cmd) + "\n")
    if fluidsynth_log_fd:
        try:
            fluidsynth_log_fd.close()
        except OSError:
            pass
    fluidsynth_log_fd = open(FLUIDSYNTH_LOG, "ab", buffering=0)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=fluidsynth_log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    bind_shell(proc.stdin)
    return proc


def _wait_fluidsynth_ready(timeout_sec: float) -> tuple[bool, str]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if fluidsynth_proc and fluidsynth_proc.poll() is not None:
            return False, "crashed"
        if find_fluidsynth_input():
            return True, "ok"
        time.sleep(0.5)
    if fluidsynth_proc and fluidsynth_proc.poll() is not None:
        return False, "crashed"
    if find_fluidsynth_input():
        return True, "ok"
    if fluidsynth_proc and fluidsynth_proc.poll() is None:
        return False, "loading"
    return False, "crashed"


def _tail_fluidsynth_log(lines: int = 15) -> list[str]:
    if not FLUIDSYNTH_LOG.is_file():
        return []
    try:
        return FLUIDSYNTH_LOG.read_text().splitlines()[-lines:]
    except OSError:
        return []


def _reap_fluidsynth():
    global fluidsynth_proc, fluidsynth_log_fd
    if fluidsynth_proc:
        if fluidsynth_proc.poll() is None:
            try:
                os.killpg(os.getpgid(fluidsynth_proc.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                fluidsynth_proc.terminate()
        try:
            fluidsynth_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(fluidsynth_proc.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                fluidsynth_proc.kill()
            fluidsynth_proc.wait(timeout=2)
        except ChildProcessError:
            pass
    fluidsynth_proc = None
    if fluidsynth_log_fd:
        try:
            fluidsynth_log_fd.close()
        except OSError:
            pass
    fluidsynth_log_fd = None
    bind_shell(None)
    clear_soundfont_state()


def _is_tabloza_fluidsynth_cmdline(cmdline: str) -> bool:
    return "midi.autoconnect=false" in cmdline


def _stop_monitor_proc():
    global midi_monitor_proc
    set_midi_monitor_input(None)
    if midi_monitor_proc and midi_monitor_proc.poll() is None:
        midi_monitor_proc.terminate()
        try:
            midi_monitor_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            midi_monitor_proc.kill()
    midi_monitor_proc = None


def stop_midi_monitor():
    global midi_monitor_thread
    midi_monitor_stop.set()
    _stop_monitor_proc()
    if (
        midi_monitor_thread
        and midi_monitor_thread.is_alive()
        and threading.current_thread() is not midi_monitor_thread
    ):
        midi_monitor_thread.join(timeout=3)
    midi_monitor_thread = None
    midi_monitor_stop.clear()


def _midi_monitor_loop():
    global midi_monitor_proc, shutdown
    monitored_key = None
    while not shutdown and not midi_monitor_stop.is_set():
        cmd, monitor_key = midi_monitor_command()
        if not cmd or not monitor_key:
            _stop_monitor_proc()
            monitored_key = None
            if midi_monitor_stop.wait(2):
                break
            continue
        if monitor_key != monitored_key:
            _stop_monitor_proc()
            monitored_key = monitor_key
            try:
                midi_monitor_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                )
                log.info("Monitor MIDI (%s)", monitor_key)
                time.sleep(0.35)
                mon = find_aseqdump_input()
                if mon:
                    set_midi_monitor_input(mon["address"])
                    tapped = refresh_midi_monitor_tap()
                    log.info(
                        "Monitor MIDI tap → %s (%d sorgenti)",
                        mon["address"],
                        tapped,
                    )
                else:
                    log.warning("Porta input aseqdump non trovata")
            except (OSError, FileNotFoundError):
                log.warning("aseqdump non disponibile — attività MIDI non monitorata")
                monitored_key = None
                if midi_monitor_stop.wait(5):
                    break
                continue
        if not midi_monitor_proc or midi_monitor_proc.poll() is not None:
            if midi_monitor_proc and midi_monitor_proc.poll() is not None and monitored_key:
                log.warning(
                    "aseqdump terminato (exit=%s, %s)",
                    midi_monitor_proc.returncode,
                    monitored_key,
                )
            monitored_key = None
            if midi_monitor_stop.wait(1):
                break
            continue
        line = midi_monitor_proc.stdout.readline()
        if not line:
            if midi_monitor_proc.poll() is not None:
                monitored_key = None
            else:
                time.sleep(0.05)
            continue
        if is_aseqdump_midi_event(line):
            touch_midi_activity()
    _stop_monitor_proc()


def start_midi_monitor():
    global midi_monitor_thread
    if midi_monitor_thread and midi_monitor_thread.is_alive():
        return
    midi_monitor_stop.clear()
    midi_monitor_thread = threading.Thread(target=_midi_monitor_loop, daemon=True)
    midi_monitor_thread.start()


def stop_fluidsynth(*, shutdown_monitor: bool = False):
    global fluidsynth_proc
    if shutdown_monitor:
        stop_midi_monitor()
    else:
        _stop_monitor_proc()
    _reap_fluidsynth()


def apply_volume(config: dict):
    from audio_utils import apply_output_volume

    vol = config.get("volume", 100)
    ok, detail = apply_output_volume(vol, config)
    if not ok:
        log.warning("Volume ALSA non impostato: %s", detail)
    max_gain = config.get("fluidsynth", {}).get("gain", 2.0)
    set_fluidsynth_output_level(vol, max_gain=max_gain)


def stop_foreign_fluidsynth():
    global fluidsynth_proc
    own_pid = (
        fluidsynth_proc.pid
        if fluidsynth_proc and fluidsynth_proc.poll() is None
        else None
    )
    try:
        result = subprocess.run(
            ["pgrep", "-x", "fluidsynth"],
            capture_output=True, text=True, timeout=3,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return
    for pid_str in result.stdout.split():
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if own_pid and pid == own_pid:
            continue
        try:
            status = Path(f"/proc/{pid}/status").read_text()
            if "zombie" in status.lower():
                continue
        except OSError:
            pass
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("latin-1")
        except OSError:
            cmdline = ""
        if _is_tabloza_fluidsynth_cmdline(cmdline):
            continue
        log.warning(
            "Arresto FluidSynth esterno PID %d (%s)",
            pid, cmdline.replace("\0", " ")[:100],
        )
        subprocess.run(["kill", "-TERM", str(pid)], timeout=3, check=False)
    time.sleep(0.5)


def fluidsynth_engine_running() -> bool:
    return fluidsynth_proc is not None and fluidsynth_proc.poll() is None


def _process_alive() -> bool:
    return fluidsynth_engine_running()


def _eject_soundfont_state() -> bool:
    """Unload SF2 from FluidSynth RAM and clear loading state."""
    ok, detail = unload_all_soundfonts(_process_alive)
    write_soundfont_state(
        selected="", loaded="", loading=False, error=None, load_started_at=None,
        load_progress=None, load_ram_baseline_mb=None, load_expected_mb=None,
    )
    if ok:
        log.info("SoundFont espulso (reset synth)")
        log_event("orchestrator", "SoundFont espulso")
        return True
    write_soundfont_state(loading=False, error=detail)
    log.error("Espulsione SF2 fallita: %s", detail)
    return False


def apply_soundfont_from_config() -> bool:
    """Carica o scarica il SoundFont indicato in config (non riavvia FluidSynth)."""
    config = load_config()
    selected = config.get("active_soundfont", "")

    if not fluidsynth_engine_running():
        log.warning("Richiesto caricamento SF2 ma FluidSynth non è attivo")
        clear_cancel_soundfont_load()
        return False
    if not shell_bound():
        log.warning("Shell FluidSynth non collegata")
        clear_cancel_soundfont_load()
        return False

    with soundfont_load_lock:
        if cancel_soundfont_load_requested():
            clear_cancel_soundfont_load()
            return _eject_soundfont_state()

        write_soundfont_state(
            selected=selected, loaded="", loading=True, error=None,
            load_started_at=time.time(),
        )
        if not selected:
            return _eject_soundfont_state()

        path = SOUNDFONTS_DIR / selected
        ok, detail = load_soundfont(
            path,
            _process_alive,
            should_cancel=cancel_soundfont_load_requested,
        )
        if not ok and detail == "cancelled":
            clear_cancel_soundfont_load()
            log.info("Caricamento SF2 annullato: %s", selected)
            log_event("orchestrator", f"Caricamento SF2 annullato: {selected}")
            return _eject_soundfont_state()
        if ok:
            write_soundfont_state(loaded=selected, loading=False, error=None)
            log.info("SoundFont caricato: %s", selected)
            log_event("orchestrator", f"SoundFont caricato: {selected}")
            apply_volume(config)
            route_rtpmidi_to_fluidsynth()
            return True
        write_soundfont_state(loaded="", loading=False, error=detail)
        log.error("Caricamento SF2 fallito: %s", detail)
        return False


def _load_soundfont_async():
    apply_soundfont_from_config()


def schedule_startup_soundfont():
    """Load default (or last active) SoundFont after FluidSynth is up."""
    config = load_config()
    name = startup_soundfont_name(config, SOUNDFONTS_DIR)
    if not name:
        return
    if config.get("active_soundfont") != name:
        config["active_soundfont"] = name
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    write_soundfont_state(
        selected=name, loaded="", loading=False, error=None, load_started_at=None,
    )
    log.info("Caricamento SF2 all'avvio: %s", name)
    log_event("orchestrator", f"Caricamento SF2 all'avvio: {name}")
    threading.Thread(target=_load_soundfont_async, daemon=True).start()


def start_fluidsynth(config: dict) -> bool:
    global fluidsynth_proc, fluidsynth_restart_after
    from audio_utils import apply_audio_fallback_if_needed

    config, fallback_used, fallback_msg = apply_audio_fallback_if_needed(config)
    if fallback_used:
        log.warning(fallback_msg)
        log_event("orchestrator", fallback_msg, "error")

    _ensure_alsa_seq()
    stop_foreign_fluidsynth()
    stop_fluidsynth()

    cmd = build_fluidsynth_cmd(config)
    log.info("Avvio FluidSynth (senza SoundFont)")
    fluidsynth_proc = _launch_fluidsynth(cmd)

    _, status = _wait_fluidsynth_ready(FLUID_STARTUP_TIMEOUT)
    if status == "crashed":
        code = fluidsynth_proc.poll() if fluidsynth_proc else None
        log.error("FluidSynth terminato durante l'avvio (exit=%s)", code)
        for line in _tail_fluidsynth_log():
            log.error("fluidsynth: %s", line)
        _reap_fluidsynth()
        fluidsynth_restart_after = time.time() + FLUID_RESTART_BACKOFF_SEC
        return False
    if status == "loading":
        log.warning("FluidSynth avviato ma porta MIDI non ancora pronta")
        return True

    if find_fluidsynth_input():
        log.info("FluidSynth pronto (porta MIDI ALSA)")
    else:
        log.error("Porta MIDI FluidSynth non trovata dopo l'avvio")
        for line in _tail_fluidsynth_log(10):
            log.error("fluidsynth: %s", line)

    write_soundfont_state(
        selected=config.get("active_soundfont", ""),
        loaded="",
        loading=False,
        error=None,
        load_started_at=None,
    )
    _apply_midi_jitter_buffer(config)
    _apply_ws_midi_gateway(config)
    reconnect_jitter_buffer_output()
    refresh_midi_routes()
    apply_volume(config)
    ok, detail = apply_runtime_synth_settings(config.get("fluidsynth", {}))
    if not ok:
        log.warning("Impostazioni synth runtime non applicate: %s", detail)
    log.info("FluidSynth avviato — seleziona e carica un SoundFont dal pannello web")
    fluidsynth_restart_after = 0.0
    return True


def handle_sighup(signum, frame):
    log.info("SIGHUP ricevuto — caricamento SoundFont")
    threading.Thread(target=_load_soundfont_async, daemon=True).start()


def handle_sigusr1(signum, frame):
    if STOP_SYNTH_NOTES_FLAG.is_file():
        STOP_SYNTH_NOTES_FLAG.unlink(missing_ok=True)
        log.info("SIGUSR1 — stop note (reset synth)")
        if not fluidsynth_engine_running() or not shell_bound():
            log.warning("Stop note ignorato — FluidSynth non pronto")
            return
        ok, detail = reset_synth(_process_alive)
        if ok:
            log.info("Tutte le note silenziate")
            log_event("orchestrator", "Note silenziate (reset synth)")
        else:
            log.warning("Reset synth fallito: %s", detail)
        return
    log.info("SIGUSR1 ricevuto — nota di test")
    state = read_soundfont_state()
    if not state.get("loaded"):
        log.warning("Nota di test ignorata — nessun SoundFont caricato")
        return
    ok, detail = send_test_note()
    if ok:
        log.info("Nota di test OK (%s)", detail)
    else:
        log.warning("Nota di test fallita: %s", detail)


def _apply_midi_settings():
    config = load_config()
    _apply_midi_jitter_buffer(config)
    _apply_ws_midi_gateway(config)
    reconnect_jitter_buffer_output()
    refresh_midi_routes()
    log.info("Impostazioni MIDI applicate (buffer=%s, bank=%s)",
             get_jitter_buffer_ms(config), get_midi_bank_select(config))
    log_event("orchestrator", "Impostazioni MIDI aggiornate")


def handle_sigusr2(signum, frame):
    global reload_fluidsynth_pending
    if RELOAD_FLUIDSYNTH_FLAG.is_file():
        RELOAD_FLUIDSYNTH_FLAG.unlink(missing_ok=True)
        reload_fluidsynth_pending = True
        log.info("SIGUSR2 — richiesto riavvio FluidSynth (nuova uscita audio)")
        log_event("orchestrator", "Riavvio FluidSynth richiesto (cambio uscita audio)")
        return
    from midi_utils import APPLY_MIDI_SETTINGS_FLAG
    if APPLY_MIDI_SETTINGS_FLAG.is_file():
        APPLY_MIDI_SETTINGS_FLAG.unlink(missing_ok=True)
        log.info("SIGUSR2 — applica impostazioni MIDI")
        _apply_midi_settings()
        return
    if APPLY_SYNTH_SETTINGS_FLAG.is_file():
        APPLY_SYNTH_SETTINGS_FLAG.unlink(missing_ok=True)
        log.info("SIGUSR2 — applica impostazioni synth")
        _apply_runtime_synth_settings()
        return
    from midi_utils import QUERY_SYNTH_EFFECTS_FLAG, SYNTH_EFFECTS_RUNTIME_FILE
    if QUERY_SYNTH_EFFECTS_FLAG.is_file():
        QUERY_SYNTH_EFFECTS_FLAG.unlink(missing_ok=True)
        _query_runtime_synth_effects()
        return
    log.info("SIGUSR2 ricevuto — applica volume")
    apply_volume(load_config())


def _apply_runtime_synth_settings():
    if not fluidsynth_engine_running() or not shell_bound():
        log.warning("Impostazioni synth non applicate — FluidSynth non pronto")
        return
    config = load_config()
    ok, detail = apply_runtime_synth_settings(config.get("fluidsynth", {}))
    if ok:
        log.info("Impostazioni synth applicate")
        log_event("orchestrator", "Impostazioni motore synth aggiornate")
    else:
        log.warning("Impostazioni synth fallite: %s", detail)


def _query_runtime_synth_effects():
    from fluidsynth_client import query_effect_settings
    from midi_utils import SYNTH_EFFECTS_RUNTIME_FILE

    if not fluidsynth_engine_running() or not shell_bound():
        log.warning("Query effetti synth non eseguita — FluidSynth non pronto")
        return
    effects = query_effect_settings()
    if not effects:
        log.warning("Query effetti synth fallita")
        return
    payload = {
        "queried_at": time.time(),
        "effects": effects,
    }
    try:
        SYNTH_EFFECTS_RUNTIME_FILE.write_text(json.dumps(payload, indent=2))
        log.info("Effetti synth runtime salvati (%d parametri)", len(effects))
    except OSError as exc:
        log.warning("Impossibile salvare effetti synth runtime: %s", exc)


def _process_pending_fluidsynth_reload():
    global reload_fluidsynth_pending
    if not reload_fluidsynth_pending:
        return
    reload_fluidsynth_pending = False
    config = load_config()
    if start_fluidsynth(config):
        log_event("orchestrator", "FluidSynth riavviato")
        schedule_startup_soundfont()
    else:
        log.error("Riavvio FluidSynth fallito — controlla %s", FLUIDSYNTH_LOG)
        log_event("orchestrator", f"Riavvio FluidSynth fallito — vedi {FLUIDSYNTH_LOG}", "error")


def handle_sigterm(signum, frame):
    global shutdown
    log.info("Arresto orchestratore...")
    shutdown = True
    stop_jitter_buffer()
    stop_fluidsynth(shutdown_monitor=True)


def _check_soundfont_load_watchdog():
    """Sblocca stato 'loading' se FluidSynth è morto o il caricamento è troppo lungo."""
    state = read_soundfont_state()
    if not state.get("loading"):
        return
    started = state.get("load_started_at")
    selected = state.get("selected", "")
    if not fluidsynth_engine_running():
        write_soundfont_state(
            loading=False, loaded="", error="FluidSynth terminato durante il caricamento",
        )
        return
    if started and selected:
        path = SOUNDFONTS_DIR / selected
        max_wait = load_timeout_for(path) + 45 if path.is_file() else 300
        if time.time() - float(started) > max_wait:
            write_soundfont_state(
                loading=False, loaded="",
                error=f"Timeout caricamento {selected} ({int(max_wait)}s)",
            )


_last_sf2_reconcile = 0.0


def _reconcile_loaded_soundfont():
    """Allinea lo stato UI se FluidSynth non ha più lo SF2 atteso in memoria."""
    global _last_sf2_reconcile
    now = time.time()
    if now - _last_sf2_reconcile < 12.0:
        return
    _last_sf2_reconcile = now

    state = read_soundfont_state()
    if state.get("loading") or not state.get("loaded"):
        return
    if not fluidsynth_engine_running() or not shell_bound():
        return

    path = SOUNDFONTS_DIR / state["loaded"]
    ok, detail = verify_soundfont_loaded(path)
    if ok:
        return

    write_soundfont_state(loaded="", error=f"SF2 non in memoria: {detail}")
    log.warning("Reconcile SF2: %s", detail)
    log_event("orchestrator", f"SF2 non in memoria: {detail}", "error")


def main():
    signal.signal(signal.SIGHUP, handle_sighup)
    signal.signal(signal.SIGUSR1, handle_sigusr1)
    signal.signal(signal.SIGUSR2, handle_sigusr2)
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    config = load_config()
    log_event("orchestrator", "Orchestrator avviato")
    started = start_fluidsynth(config)
    start_midi_monitor()
    if started:
        schedule_startup_soundfont()

    while not shutdown:
        _process_pending_fluidsynth_reload()
        if fluidsynth_proc is None or fluidsynth_proc.poll() is not None:
            if time.time() < fluidsynth_restart_after:
                time.sleep(ROUTING_INTERVAL)
                continue
            if fluidsynth_proc and fluidsynth_proc.poll() is not None:
                code = fluidsynth_proc.returncode
                log.warning("FluidSynth terminato (exit %s), riavvio...", code)
                for line in _tail_fluidsynth_log(8):
                    log.warning("fluidsynth: %s", line)
                _reap_fluidsynth()
            else:
                log.warning("FluidSynth non attivo — tentativo avvio...")
            if start_fluidsynth(load_config()):
                schedule_startup_soundfont()
        else:
            route_rtpmidi_to_fluidsynth()
            _check_soundfont_load_watchdog()
            _reconcile_loaded_soundfont()
        time.sleep(ROUTING_INTERVAL)

    log.info("Orchestratore arrestato.")


if __name__ == "__main__":
    main()

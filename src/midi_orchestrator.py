#!/usr/bin/env python3
"""Tabloza MidiExpander — MIDI/Audio orchestrator.

Avvia FluidSynth senza SoundFont; il caricamento SF2 avviene su richiesta (UI / SIGHUP).

GPIO UART MIDI: planned — see docs/TODO.md
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

from activity_status import touch_midi_activity
from fluidsynth_client import (
    clear_soundfont_state,
    load_soundfont,
    read_soundfont_state,
    reset_synth,
    server_ready,
    write_soundfont_state,
)
from midi_utils import find_fluidsynth_input, route_rtpmidi_to_fluidsynth, send_cc7, send_test_note

DATA_DIR = Path(os.environ.get("TABLOZA_DATA_DIR", "/var/lib/tabloza"))
CONFIG_FILE = DATA_DIR / "config.json"
SOUNDFONTS_DIR = DATA_DIR / "soundfonts"

FLUIDSYNTH_BIN = "/usr/bin/fluidsynth"
FLUIDSYNTH_LOG = Path("/run/tabloza/fluidsynth.log")
FLUID_STARTUP_TIMEOUT = 15.0
ROUTING_INTERVAL = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [orchestrator] %(levelname)s: %(message)s",
)
log = logging.getLogger("tabloza.orchestrator")

fluidsynth_proc: subprocess.Popen | None = None
fluidsynth_log_fd = None
shutdown = False
midi_monitor_proc: subprocess.Popen | None = None
midi_monitor_thread: threading.Thread | None = None
soundfont_load_lock = threading.Lock()


def load_config() -> dict:
    defaults = {
        "active_soundfont": "",
        "volume": 100,
        "fluidsynth": {
            "audio_driver": "alsa",
            "audio_device": "plughw:0,0",
            "sample_rate": 44100,
            "period_size": 256,
            "period_count": 4,
            "gain": 0.5,
        },
    }
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            stored = json.load(f)
        defaults.update(stored)
        if "fluidsynth" in stored:
            defaults["fluidsynth"].update(stored["fluidsynth"])
    return defaults


def build_fluidsynth_cmd(config: dict) -> list[str]:
    """FluidSynth senza SF2 — caricamento dinamico via server TCP."""
    fs_cfg = config.get("fluidsynth", {})
    return [
        FLUIDSYNTH_BIN,
        "-a", fs_cfg.get("audio_driver", "alsa"),
        "-o", f"audio.alsa.device={fs_cfg.get('audio_device', 'plughw:0,0')}",
        "-r", str(fs_cfg.get("sample_rate", 44100)),
        "-z", str(fs_cfg.get("period_size", 256)),
        "-c", str(fs_cfg.get("period_count", 4)),
        "-g", str(fs_cfg.get("gain", 0.5)),
        "-m", "alsa_seq",
        "-o", "midi.autoconnect=false",
        "-o", "synth.dynamic-sample-loading=yes",
        "-s", "-p", "9800",
        "-ni",
    ]


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
    return subprocess.Popen(
        cmd,
        stdout=fluidsynth_log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _wait_fluidsynth_ready(timeout_sec: float) -> tuple[bool, str]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if fluidsynth_proc and fluidsynth_proc.poll() is not None:
            return False, "crashed"
        if find_fluidsynth_input() and server_ready():
            return True, "ok"
        time.sleep(0.5)
    if fluidsynth_proc and fluidsynth_proc.poll() is not None:
        return False, "crashed"
    if find_fluidsynth_input() and server_ready():
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
    clear_soundfont_state()


def _is_tabloza_fluidsynth_cmdline(cmdline: str) -> bool:
    return "midi.autoconnect=false" in cmdline or "9800" in cmdline


def _stop_monitor_proc():
    global midi_monitor_proc
    if midi_monitor_proc and midi_monitor_proc.poll() is None:
        midi_monitor_proc.terminate()
        try:
            midi_monitor_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            midi_monitor_proc.kill()
    midi_monitor_proc = None


def stop_midi_monitor():
    global midi_monitor_thread
    _stop_monitor_proc()
    if (
        midi_monitor_thread
        and midi_monitor_thread.is_alive()
        and threading.current_thread() is not midi_monitor_thread
    ):
        midi_monitor_thread.join(timeout=2)
    midi_monitor_thread = None


def _midi_monitor_loop():
    global midi_monitor_proc, shutdown
    monitored_port = None
    while not shutdown:
        fs = find_fluidsynth_input()
        if not fs:
            _stop_monitor_proc()
            monitored_port = None
            time.sleep(2)
            continue
        if monitored_port != fs["address"]:
            _stop_monitor_proc()
            monitored_port = fs["address"]
            try:
                midi_monitor_proc = subprocess.Popen(
                    ["aseqdump", "-p", fs["address"]],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                log.info("Monitor MIDI su porta %s", fs["address"])
            except (OSError, FileNotFoundError):
                time.sleep(2)
                continue
        if not midi_monitor_proc or midi_monitor_proc.poll() is not None:
            monitored_port = None
            time.sleep(1)
            continue
        line = midi_monitor_proc.stdout.readline()
        if not line:
            continue
        if line.startswith("Waiting") or line.startswith("Source"):
            continue
        if line.strip():
            touch_midi_activity()


def start_midi_monitor():
    global midi_monitor_thread
    if midi_monitor_thread and midi_monitor_thread.is_alive():
        return
    midi_monitor_thread = threading.Thread(target=_midi_monitor_loop, daemon=True)
    midi_monitor_thread.start()


def stop_fluidsynth():
    global fluidsynth_proc
    stop_midi_monitor()
    _reap_fluidsynth()


def apply_volume(config: dict):
    vol = config.get("volume", 100)
    send_cc7(vol)


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


def apply_soundfont_from_config() -> bool:
    """Carica o scarica il SoundFont indicato in config (non riavvia FluidSynth)."""
    config = load_config()
    selected = config.get("active_soundfont", "")

    if not fluidsynth_engine_running():
        log.warning("Richiesto caricamento SF2 ma FluidSynth non è attivo")
        return False
    if not server_ready():
        log.warning("Server FluidSynth TCP non pronto")
        return False

    with soundfont_load_lock:
        write_soundfont_state(selected=selected, loading=True, error=None)
        if not selected:
            ok, detail = reset_synth()
            if ok:
                write_soundfont_state(loaded="", loading=False, error=None)
                log.info("SoundFont scaricato (reset synth)")
                return True
            write_soundfont_state(loaded="", loading=False, error=detail)
            log.error("Reset synth fallito: %s", detail)
            return False

        path = SOUNDFONTS_DIR / selected
        ok, detail = load_soundfont(path)
        if ok:
            write_soundfont_state(loaded=selected, loading=False, error=None)
            log.info("SoundFont caricato: %s", selected)
            apply_volume(config)
            route_rtpmidi_to_fluidsynth()
            return True
        write_soundfont_state(loaded="", loading=False, error=detail)
        log.error("Caricamento SF2 fallito: %s", detail)
        return False


def _load_soundfont_async():
    apply_soundfont_from_config()


def start_fluidsynth(config: dict) -> bool:
    global fluidsynth_proc
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
        return False
    if status == "loading":
        log.warning("FluidSynth avviato ma porta MIDI/server non ancora pronti")
        return True

    write_soundfont_state(selected=config.get("active_soundfont", ""), loaded="", loading=False)
    route_rtpmidi_to_fluidsynth()
    log.info("FluidSynth pronto — seleziona un SoundFont dal pannello web")
    return True


def handle_sighup(signum, frame):
    log.info("SIGHUP ricevuto — caricamento SoundFont")
    threading.Thread(target=_load_soundfont_async, daemon=True).start()


def handle_sigusr1(signum, frame):
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


def handle_sigterm(signum, frame):
    global shutdown
    log.info("Arresto orchestratore...")
    shutdown = True
    stop_fluidsynth()


def main():
    signal.signal(signal.SIGHUP, handle_sighup)
    signal.signal(signal.SIGUSR1, handle_sigusr1)
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    config = load_config()
    start_fluidsynth(config)
    start_midi_monitor()

    while not shutdown:
        if fluidsynth_proc is None or fluidsynth_proc.poll() is not None:
            if fluidsynth_proc and fluidsynth_proc.poll() is not None:
                code = fluidsynth_proc.returncode
                log.warning("FluidSynth terminato (exit %s), riavvio...", code)
                for line in _tail_fluidsynth_log(8):
                    log.warning("fluidsynth: %s", line)
                _reap_fluidsynth()
            else:
                log.warning("FluidSynth non attivo — tentativo avvio...")
            start_fluidsynth(load_config())
        else:
            route_rtpmidi_to_fluidsynth()
        time.sleep(ROUTING_INTERVAL)

    log.info("Orchestratore arrestato.")


if __name__ == "__main__":
    main()

"""Tabloza MidiExpander — ALSA MIDI utilities."""

import logging
import os
import re
import signal
import subprocess
import time
from pathlib import Path

from activity_status import touch_midi_activity

log = logging.getLogger("tabloza.midi")

RELOAD_FLUIDSYNTH_FLAG = Path("/run/tabloza/reload_fluidsynth")

PORT_RE = re.compile(r"(\d+:\d+)")
CLIENT_RE = re.compile(r"^client (\d+):\s*'([^']*)'")
CLIENT_NUM_RE = re.compile(r"^client (\d+):")
PORT_LINE_RE = re.compile(r"^\s+(\d+)\s+'([^']*)'")


def _run_aconnect(flag: str) -> str:
    try:
        result = subprocess.run(
            ["aconnect", flag],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _parse_ports(output: str) -> list[dict]:
    """Parse aconnect output into {name, address} dicts.

    ALSA prints client id on one line and port index on the next, e.g.:
      client 128: 'FLUID Synth' [...]
          0 'Synth input port (fluid_synth)' [...]
    Address is 128:0, not present as a single token on either line.
    """
    ports = []
    client_num = None
    client_name = ""
    for line in output.splitlines():
        client_match = CLIENT_RE.match(line)
        if client_match:
            client_num = client_match.group(1)
            client_name = client_match.group(2)
            continue
        num_match = CLIENT_NUM_RE.match(line)
        if num_match and not line.startswith(" "):
            client_num = num_match.group(1)
            name_match = re.search(r"'([^']*)'", line)
            client_name = name_match.group(1) if name_match else ""
            continue
        port_match = PORT_LINE_RE.match(line)
        if port_match and client_num is not None:
            ports.append({
                "client": client_name,
                "name": port_match.group(2),
                "address": f"{client_num}:{port_match.group(1)}",
            })
    return ports


def get_output_ports() -> list[dict]:
    return _parse_ports(_run_aconnect("-o"))


def get_input_ports() -> list[dict]:
    return _parse_ports(_run_aconnect("-i"))


def find_fluidsynth_input() -> dict | None:
    """Return FluidSynth ALSA port for routing MIDI into the synth.

    FluidSynth 2.4 registers "Synth input port" as an output endpoint in
    `aconnect -o`, not in `aconnect -i`. rtpmidid may mirror that name on its
    own client — always prefer the real FluidSynth client.
    """
    def _is_fluidsynth_client(port: dict) -> bool:
        return port["client"].lower().startswith("fluid synth")

    def _is_fluidsynth_port(port: dict) -> bool:
        label = f"{port['client']} {port['name']}".lower()
        if "rtpmidid" in label:
            return False
        return "fluid" in label or "synth input" in label

    for port in get_output_ports():
        if _is_fluidsynth_client(port):
            return port
    for port in get_input_ports():
        if _is_fluidsynth_client(port):
            return port
    for port in get_output_ports():
        if _is_fluidsynth_port(port):
            return port
    for port in get_input_ports():
        if _is_fluidsynth_port(port):
            return port
    return None


def find_rtpmidid_outputs() -> list[dict]:
    """All ALSA output ports from rtpmidid (incl. per-connection ports from Mac)."""
    sources = []
    for port in get_output_ports():
        label = f"{port['client']} {port['name']}".lower()
        if "rtpmidid" in label:
            sources.append(port)
    return sources


def get_active_routes() -> list[dict]:
    """Return rtpmidid → fluidsynth connections from `aconnect -l`."""
    try:
        result = subprocess.run(
            ["aconnect", "-l"],
            capture_output=True, text=True, timeout=5,
        )
        output = result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    fs = find_fluidsynth_input()
    if not fs:
        return []

    routes = []
    fs_addr = fs["address"]
    in_fluid_client = False
    for line in output.splitlines():
        client_match = CLIENT_RE.match(line)
        if client_match:
            in_fluid_client = client_match.group(2).lower().startswith("fluid synth")
            continue
        if in_fluid_client and "Connected From:" in line:
            for addr in PORT_RE.findall(line.split("Connected From:", 1)[1]):
                routes.append({"from": addr, "to": fs_addr})
            break
        if in_fluid_client and "Connecting To:" in line and fs_addr in line:
            for addr in PORT_RE.findall(line.split("Connecting To:", 1)[1]):
                if addr != fs_addr:
                    routes.append({"from": fs_addr, "to": addr})
    return routes


def get_midi_status() -> dict:
    """Return structured MIDI routing status for API/frontend."""
    fs = find_fluidsynth_input()
    rtp_sources = find_rtpmidid_outputs()
    active_routes = get_active_routes()
    routes = []
    if rtp_sources:
        any_connected = any(
            any(r["from"] == src["address"] for r in active_routes)
            for src in rtp_sources
        )
        routes.append({
            "type": "rtpmidi",
            "name": "rtpmidid",
            "address": rtp_sources[0]["address"],
            "status": "connected" if any_connected else "available",
            "port_count": len(rtp_sources),
        })
    routes.append({
        "type": "gpio",
        "name": "MIDI GPIO (UART)",
        "address": None,
        "status": "planned",
    })
    return {
        "fluidsynth": fs,
        "sources": routes,
        "active_routes": active_routes,
        "routing_ok": fs is not None and len(active_routes) > 0,
    }


def route_rtpmidi_to_fluidsynth() -> int:
    """Connect rtpmidid outputs to FluidSynth input. Returns number of routes made."""
    fs = find_fluidsynth_input()
    if not fs:
        return 0
    count = 0
    for src in find_rtpmidid_outputs():
        try:
            subprocess.run(
                ["aconnect", src["address"], fs["address"]],
                capture_output=True, timeout=3, check=False,
            )
            log.info("Routed %s → %s", src["address"], fs["address"])
            count += 1
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return count


def volume_to_gain(volume: int, max_gain: float = 2.0) -> float:
    vol = max(0, min(127, int(volume)))
    return round((vol / 127.0) * max_gain, 3)


def set_fluidsynth_output_level(
    volume: int,
    max_gain: float = 2.0,
    retries: int = 5,
    delay: float = 0.5,
) -> bool:
    """Keep FluidSynth at full internal level; ALSA mixer handles loudness."""
    from fluidsynth_client import send_command, shell_bound

    gain = max_gain if max(0, min(127, int(volume))) > 0 else 0.0
    for attempt in range(retries):
        if shell_bound() and find_fluidsynth_input():
            ok_gain, _ = send_command(f"gain {gain}")
            if ok_gain:
                log.info("FluidSynth gain=%.3f (volume master via ALSA)", gain)
                return True
        if attempt < retries - 1:
            time.sleep(delay)
    log.warning("Impossibile impostare gain FluidSynth (volume=%d)", volume)
    return False


def set_master_volume(
    volume: int,
    max_gain: float = 2.0,
    retries: int = 5,
    delay: float = 0.5,
) -> bool:
    """Backward-compatible alias — only adjusts FluidSynth gain."""
    return set_fluidsynth_output_level(volume, max_gain=max_gain, retries=retries, delay=delay)


def send_cc7(volume: int, retries: int = 5, delay: float = 1.0) -> bool:
    """Backward-compatible alias for set_master_volume."""
    return set_master_volume(volume, max_gain=2.0, retries=retries, delay=delay)


def trigger_orchestrator_apply_volume() -> bool:
    """Ask tabloza-orchestrator to apply volume from config (SIGUSR2)."""
    try:
        result = subprocess.run(
            ["systemctl", "show", "tabloza-orchestrator", "-p", "MainPID", "--value"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        pid = int(result.stdout.strip())
        if pid <= 0:
            return False
        RELOAD_FLUIDSYNTH_FLAG.unlink(missing_ok=True)
        os.kill(pid, signal.SIGUSR2)
        return True
    except (OSError, ValueError, subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return False


def trigger_orchestrator_reload_fluidsynth() -> bool:
    """Restart FluidSynth in orchestrator (SIGUSR2 + flag) — e.g. after audio output change."""
    try:
        result = subprocess.run(
            ["systemctl", "show", "tabloza-orchestrator", "-p", "MainPID", "--value"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        pid = int(result.stdout.strip())
        if pid <= 0:
            return False
        RELOAD_FLUIDSYNTH_FLAG.parent.mkdir(parents=True, exist_ok=True)
        RELOAD_FLUIDSYNTH_FLAG.write_text("1")
        os.kill(pid, signal.SIGUSR2)
        return True
    except (OSError, ValueError, subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return False


def wait_fluidsynth_midi_ready(timeout: float = 45.0) -> bool:
    """Poll until FluidSynth ALSA MIDI port is visible."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if find_fluidsynth_input():
            return True
        time.sleep(0.5)
    return False


def send_test_note(retries: int = 5, delay: float = 0.6) -> tuple[bool, str]:
    """Play a short C4 test note on FluidSynth via shell. Returns (ok, detail)."""
    from fluidsynth_client import read_soundfont_state, send_command, shell_bound

    last_detail = "Porta MIDI FluidSynth non trovata"
    for attempt in range(retries):
        fs = find_fluidsynth_input()
        if not fs:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            if not _fluidsynth_process_running():
                return False, "FluidSynth non in esecuzione"
            sf_state = read_soundfont_state()
            if not sf_state.get("loaded"):
                return False, "Nessun SoundFont caricato — seleziona e premi Carica nel pannello"
            return False, "Porta MIDI FluidSynth non pronta — attendi e riprova"
        if not shell_bound():
            last_detail = "Shell FluidSynth non collegata"
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            return False, last_detail
        try:
            send_command("prog 0 0")
            send_command("cc 0 7 127")
            ok, detail = send_command("noteon 0 60 127")
            if not ok:
                raise RuntimeError(detail)
            touch_midi_activity()
            time.sleep(1.2)
            send_command("noteoff 0 60")
            log.info("Nota di test inviata via shell FluidSynth (%s)", fs["address"])
            return True, fs["address"]
        except (RuntimeError, OSError) as exc:
            last_detail = str(exc)
            if attempt < retries - 1:
                time.sleep(delay)
    return False, last_detail


def _fluidsynth_process_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-x", "fluidsynth"],
            capture_output=True, text=True, timeout=3,
        )
        for pid_str in result.stdout.split():
            try:
                status = Path(f"/proc/{pid_str}/status").read_text()
            except OSError:
                continue
            if "zombie" in status.lower():
                continue
            return True
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def trigger_orchestrator_test_note() -> bool:
    """Ask tabloza-orchestrator main process to play the test note (SIGUSR1).

    Must target MainPID only — systemctl kill would signal the whole cgroup
    and kill FluidSynth too (SIGUSR1 = signal 10).
    """
    try:
        result = subprocess.run(
            ["systemctl", "show", "tabloza-orchestrator", "-p", "MainPID", "--value"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        pid = int(result.stdout.strip())
        if pid <= 0:
            return False
        os.kill(pid, signal.SIGUSR1)
        return True
    except (OSError, ValueError, subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return False

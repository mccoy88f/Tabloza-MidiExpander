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
APPLY_SYNTH_SETTINGS_FLAG = Path("/run/tabloza/apply_synth_settings")
APPLY_MIDI_SETTINGS_FLAG = Path("/run/tabloza/apply_midi_settings")
STOP_SYNTH_NOTES_FLAG = Path("/run/tabloza/synth_stop_notes")

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


_RESERVED_MIDI_CLIENTS = (
    "fluid synth",
    "rtpmidid",
    "tabloza buffer",
    "midi through",
    "system",
    "sampler",
    "virmidi",
    "dummy",
)


def _is_reserved_midi_client(client_name: str) -> bool:
    label = client_name.lower()
    return any(token in label for token in _RESERVED_MIDI_CLIENTS)


def find_usb_midi_outputs() -> list[dict]:
    """Hardware/USB ALSA MIDI sources (parallel to rtpmidid network MIDI)."""
    sources = []
    for port in get_output_ports():
        if _is_reserved_midi_client(port["client"]):
            continue
        label = f"{port['client']} {port['name']}".lower()
        if "rtpmidid" in label or "fluid" in label or "synth input" in label:
            continue
        sources.append(port)
    return sources


def _midi_sources_for_routing() -> list[dict]:
    return find_rtpmidid_outputs() + find_usb_midi_outputs()


def _aconnect_list_output() -> str:
    try:
        result = subprocess.run(
            ["aconnect", "-l"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def disconnect_source_routes(src_addr: str) -> int:
    """Remove all ALSA routes from a MIDI source (clears stale FluidSynth clients)."""
    output = _aconnect_list_output()
    if not output:
        return 0

    removed = 0
    current_client_num = None
    current_port_addr = None
    for line in output.splitlines():
        client_match = CLIENT_RE.match(line)
        if client_match:
            current_client_num = client_match.group(1)
            current_port_addr = None
            continue
        num_match = CLIENT_NUM_RE.match(line)
        if num_match and not line.startswith(" "):
            current_client_num = num_match.group(1)
            current_port_addr = None
            continue
        port_match = PORT_LINE_RE.match(line)
        if port_match and current_client_num is not None:
            current_port_addr = f"{current_client_num}:{port_match.group(1)}"
            continue
        if current_port_addr == src_addr and "Connecting To:" in line:
            for dest in PORT_RE.findall(line.split("Connecting To:", 1)[1]):
                try:
                    subprocess.run(
                        ["aconnect", "-d", src_addr, dest],
                        capture_output=True, timeout=3, check=False,
                    )
                    removed += 1
                    log.info("Disconnesso MIDI %s → %s", src_addr, dest)
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
    return removed


def _route_destination() -> dict | None:
    """ALSA port where MIDI sources should connect (buffer input or FluidSynth)."""
    from midi_jitter_buffer import get_buffer_input_port

    buf = get_buffer_input_port()
    if buf:
        return buf
    return find_fluidsynth_input()


def get_active_routes() -> list[dict]:
    """Return MIDI sources connected to the active route destination."""
    dest = _route_destination()
    if not dest:
        return []

    dest_addr = dest["address"]
    source_addrs = {src["address"] for src in _midi_sources_for_routing()}
    routes = []
    current_client_num = None
    current_port_addr = None
    for line in _aconnect_list_output().splitlines():
        client_match = CLIENT_RE.match(line)
        if client_match:
            current_client_num = client_match.group(1)
            current_port_addr = None
            continue
        num_match = CLIENT_NUM_RE.match(line)
        if num_match and not line.startswith(" "):
            current_client_num = num_match.group(1)
            current_port_addr = None
            continue
        port_match = PORT_LINE_RE.match(line)
        if port_match and current_client_num is not None:
            current_port_addr = f"{current_client_num}:{port_match.group(1)}"
            continue
        if current_port_addr in source_addrs and "Connecting To:" in line:
            if dest_addr in line.split("Connecting To:", 1)[1]:
                routes.append({"from": current_port_addr, "to": dest_addr})
    return routes


def find_aseqdump_input() -> dict | None:
    """Return the ALSA input port created by the running aseqdump monitor."""
    for port in get_input_ports():
        if port["client"].lower().startswith("aseqdump"):
            return port
    return None


_midi_monitor_input: str | None = None


def set_midi_monitor_input(address: str | None) -> None:
    global _midi_monitor_input
    _midi_monitor_input = address


def refresh_midi_monitor_tap() -> int:
    """Connect rtpmidid/USB outputs to aseqdump in parallel with the synth route."""
    if not _midi_monitor_input:
        return 0
    count = 0
    for src in _midi_sources_for_routing():
        try:
            subprocess.run(
                ["aconnect", src["address"], _midi_monitor_input],
                capture_output=True, timeout=3, check=False,
            )
            count += 1
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return count


def midi_monitor_command() -> tuple[list[str], str | None]:
    """Return argv + key for the MIDI activity aseqdump process.

    aseqdump must be *tapped* into the MIDI graph via ``aconnect`` (see
    :func:`refresh_midi_monitor_tap`); running it alone does not see traffic
    copied between other ALSA clients.
    """
    if get_active_routes() or find_rtpmidid_outputs() or find_usb_midi_outputs():
        return ["aseqdump"], "tap"
    fs = find_fluidsynth_input()
    if fs:
        return ["aseqdump"], "tap"
    return [], None


def midi_monitor_port() -> tuple[str | None, str | None]:
    """Backward-compatible helper — prefer :func:`midi_monitor_command`."""
    cmd, key = midi_monitor_command()
    if not cmd:
        return None, None
    if key == "all":
        return "all", key
    if key == "tap":
        return "tap", key
    if len(cmd) == 3 and cmd[0] == "aseqdump" and cmd[1] == "-p":
        return cmd[2], key
    return None, key


def get_midi_status() -> dict:
    """Return structured MIDI routing status for API/frontend."""
    from midi_jitter_buffer import jitter_buffer_status

    fs = find_fluidsynth_input()
    rtp_sources = find_rtpmidid_outputs()
    usb_sources = find_usb_midi_outputs()
    active_routes = get_active_routes()
    buffer_status = jitter_buffer_status()
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
    if usb_sources:
        by_client: dict[str, list[dict]] = {}
        for port in usb_sources:
            by_client.setdefault(port["client"] or port["name"], []).append(port)
        for client, ports in sorted(by_client.items()):
            any_connected = any(
                any(r["from"] == port["address"] for r in active_routes)
                for port in ports
            )
            routes.append({
                "type": "usb",
                "name": client,
                "address": ports[0]["address"],
                "status": "connected" if any_connected else "available",
                "port_count": len(ports),
            })
    return {
        "fluidsynth": fs,
        "sources": routes,
        "active_routes": active_routes,
        "routing_ok": fs is not None and len(active_routes) > 0,
        "jitter_buffer": buffer_status,
    }


def get_midi_settings_for_api(config: dict) -> dict:
    from midi_config import midi_settings_for_api

    return midi_settings_for_api(config)


def route_midi_to_fluidsynth() -> int:
    """Connect network (rtpmidid) and USB MIDI sources to buffer or FluidSynth."""
    dest = _route_destination()
    if not dest:
        return 0
    count = 0
    for src in _midi_sources_for_routing():
        disconnect_source_routes(src["address"])
        try:
            subprocess.run(
                ["aconnect", src["address"], dest["address"]],
                capture_output=True, timeout=3, check=False,
            )
            log.info("Routed %s (%s) → %s", src["client"], src["address"], dest["address"])
            count += 1
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    refresh_midi_monitor_tap()
    return count


def refresh_midi_routes(retries: int = 4, delay: float = 0.6) -> int:
    """Reconnect MIDI sources after FluidSynth restart (new ALSA client id)."""
    total = 0
    for attempt in range(retries):
        total = route_midi_to_fluidsynth()
        if total and get_active_routes():
            return total
        if attempt < retries - 1:
            time.sleep(delay)
    return total


def route_rtpmidi_to_fluidsynth() -> int:
    """Backward-compatible alias — routes all MIDI sources including USB."""
    return route_midi_to_fluidsynth()


def volume_to_gain(volume: int, max_gain: float = 2.0) -> float:
    from audio_utils import normalize_volume
    vol = normalize_volume(volume)
    return round((vol / 100.0) * max_gain, 3) if vol > 0 else 0.0


def set_fluidsynth_output_level(
    volume: int,
    max_gain: float = 2.0,
    retries: int = 5,
    delay: float = 0.5,
) -> bool:
    """Keep FluidSynth at full internal level; ALSA mixer handles loudness."""
    from fluidsynth_client import send_command, shell_bound

    from audio_utils import normalize_volume
    gain = volume_to_gain(volume, max_gain)
    if normalize_volume(volume) == 0:
        gain = 0.0
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


def trigger_orchestrator_apply_midi_settings() -> bool:
    """Ask orchestrator to apply MIDI buffer/routing from config (SIGUSR2 + flag)."""
    try:
        result = subprocess.run(
            ["systemctl", "show", "tabloza-orchestrator", "-p", "MainPID", "--value"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        pid = int(result.stdout.strip())
        if pid <= 0:
            return False
        APPLY_MIDI_SETTINGS_FLAG.parent.mkdir(parents=True, exist_ok=True)
        APPLY_MIDI_SETTINGS_FLAG.write_text("1")
        os.kill(pid, signal.SIGUSR2)
        return True
    except (OSError, ValueError, subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return False


def trigger_orchestrator_apply_synth_settings() -> bool:
    """Ask orchestrator to apply runtime synth settings (SIGUSR2 + flag)."""
    try:
        result = subprocess.run(
            ["systemctl", "show", "tabloza-orchestrator", "-p", "MainPID", "--value"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        pid = int(result.stdout.strip())
        if pid <= 0:
            return False
        APPLY_SYNTH_SETTINGS_FLAG.parent.mkdir(parents=True, exist_ok=True)
        APPLY_SYNTH_SETTINGS_FLAG.write_text("1")
        os.kill(pid, signal.SIGUSR2)
        return True
    except (OSError, ValueError, subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return False


def trigger_orchestrator_stop_notes() -> bool:
    """Silence all notes via orchestrator (SIGUSR1 + flag)."""
    try:
        result = subprocess.run(
            ["systemctl", "show", "tabloza-orchestrator", "-p", "MainPID", "--value"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        pid = int(result.stdout.strip())
        if pid <= 0:
            return False
        STOP_SYNTH_NOTES_FLAG.parent.mkdir(parents=True, exist_ok=True)
        STOP_SYNTH_NOTES_FLAG.write_text("1")
        os.kill(pid, signal.SIGUSR1)
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

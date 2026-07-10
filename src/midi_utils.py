"""Tabloza MidiExpander — ALSA MIDI utilities."""

import logging
import re
import subprocess
import time

from activity_status import touch_midi_activity

log = logging.getLogger("tabloza.midi")

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
    for port in get_input_ports():
        label = f"{port['client']} {port['name']}".lower()
        if "fluid" in label:
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
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if "Connected To:" not in line or fs_addr not in line:
            continue
        for j in range(i - 1, max(i - 4, -1), -1):
            match = PORT_RE.search(lines[j])
            if match and ("'" in lines[j] or "Connected" not in lines[j]):
                routes.append({"from": match.group(1), "to": fs_addr})
                break
    return routes


def get_midi_status() -> dict:
    """Return structured MIDI routing status for API/frontend."""
    fs = find_fluidsynth_input()
    rtp_sources = find_rtpmidid_outputs()
    active_routes = get_active_routes()
    routes = []
    for src in rtp_sources:
        connected = any(r["from"] == src["address"] for r in active_routes)
        routes.append({
            "type": "rtpmidi",
            "name": src["client"],
            "address": src["address"],
            "status": "connected" if connected else "available",
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


def send_cc7(volume: int, retries: int = 5, delay: float = 1.0) -> bool:
    """Send MIDI CC7 (channel 1) to FluidSynth. Retries until port is available."""
    volume = max(0, min(127, int(volume)))
    for attempt in range(retries):
        fs = find_fluidsynth_input()
        if fs:
            try:
                subprocess.run(
                    ["amidi", "-p", fs["address"], "-S", f"B0 07 {volume:02X}"],
                    capture_output=True, timeout=3, check=True,
                )
                log.info("Volume CC7=%d inviato a %s", volume, fs["address"])
                return True
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
                pass
        if attempt < retries - 1:
            time.sleep(delay)
    log.warning("Impossibile inviare CC7 (volume=%d)", volume)
    return False


def send_test_note(retries: int = 5, delay: float = 0.6) -> tuple[bool, str]:
    """Play a short C4 test note on FluidSynth via ALSA. Returns (ok, detail)."""
    last_detail = "Porta MIDI FluidSynth non trovata"
    for attempt in range(retries):
        fs = find_fluidsynth_input()
        if not fs:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            if not _fluidsynth_process_running():
                return False, "FluidSynth non in esecuzione — carica un SF2 e riavvia l'orchestrator"
            return False, last_detail
        try:
            subprocess.run(
                ["amidi", "-p", fs["address"], "-S", "90 3C 64"],
                capture_output=True, timeout=3, check=True,
            )
            touch_midi_activity()
            time.sleep(0.35)
            subprocess.run(
                ["amidi", "-p", fs["address"], "-S", "80 3C 00"],
                capture_output=True, timeout=3, check=True,
            )
            log.info("Nota di test inviata a %s", fs["address"])
            return True, fs["address"]
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError) as exc:
            last_detail = f"amidi fallito su {fs['address']}: {exc}"
            if attempt < retries - 1:
                time.sleep(delay)
    return False, last_detail


def _fluidsynth_process_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-x", "fluidsynth"],
            capture_output=True, timeout=3,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def trigger_orchestrator_test_note() -> bool:
    """Ask tabloza-orchestrator to play the test note (SIGUSR1)."""
    try:
        subprocess.run(
            ["systemctl", "kill", "-USR1", "tabloza-orchestrator"],
            capture_output=True, timeout=5, check=True,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return False

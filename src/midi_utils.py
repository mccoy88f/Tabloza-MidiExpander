"""Tabloza MidiExpander — ALSA MIDI utilities."""

import logging
import re
import subprocess
import time

log = logging.getLogger("tabloza.midi")

PORT_RE = re.compile(r"(\d+:\d+)")


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
    """Parse aconnect output into {name, address} dicts."""
    ports = []
    client_name = ""
    for line in output.splitlines():
        if line.startswith("client "):
            parts = line.split(":", 1)
            if len(parts) > 1:
                client_name = parts[1].strip().strip("'")
            continue
        match = PORT_RE.search(line)
        if match:
            port_name = line.strip().strip("'").split("'")[0].strip("'") if "'" in line else ""
            ports.append({
                "client": client_name,
                "name": port_name or client_name,
                "address": match.group(1),
            })
    return ports


def get_output_ports() -> list[dict]:
    return _parse_ports(_run_aconnect("-o"))


def get_input_ports() -> list[dict]:
    return _parse_ports(_run_aconnect("-i"))


def find_fluidsynth_input() -> dict | None:
    for port in get_input_ports():
        label = f"{port['client']} {port['name']}".lower()
        if "fluidsynth" in label or "fluid synth" in label:
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


def get_midi_status() -> dict:
    """Return structured MIDI routing status for API/frontend."""
    fs = find_fluidsynth_input()
    rtp_sources = find_rtpmidid_outputs()
    routes = []
    for src in rtp_sources:
        routes.append({
            "type": "rtpmidi",
            "name": src["client"],
            "address": src["address"],
            "status": "available",
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
        "routing_ok": fs is not None and len(rtp_sources) > 0,
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

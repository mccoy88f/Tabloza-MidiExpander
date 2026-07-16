"""Tabloza — uscite audio Bluetooth via PulseAudio / PipeWire (pactl)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

log = logging.getLogger("tabloza.bluetooth")

PULSE_DEVICE_PREFIX = "pulse:"
# Sink BlueZ tipici: bluez_sink.* / bluez_output.*
BLUEZ_SINK_RE = re.compile(r"bluez", re.IGNORECASE)


def is_pulse_device_id(device_id: str) -> bool:
    return (device_id or "").strip().startswith(PULSE_DEVICE_PREFIX)


def pulse_sink_from_device_id(device_id: str) -> str:
    raw = (device_id or "").strip()
    if raw.startswith(PULSE_DEVICE_PREFIX):
        return raw[len(PULSE_DEVICE_PREFIX):].strip()
    return raw


def pulse_device_id(sink_name: str) -> str:
    return f"{PULSE_DEVICE_PREFIX}{sink_name.strip()}"


def pulse_available() -> bool:
    return shutil.which("pactl") is not None


def _run(cmd: list[str], timeout: float = 8) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _pactl_short_sinks() -> list[tuple[str, str]]:
    """Return [(name, state)] from `pactl list short sinks`."""
    if not pulse_available():
        return []
    result = _run(["pactl", "list", "short", "sinks"])
    if result.returncode != 0:
        return []
    sinks: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        # index name module sample_spec state
        name = parts[1]
        state = parts[-1] if len(parts) >= 5 else ""
        sinks.append((name, state))
    return sinks


def _sink_description(sink_name: str) -> str:
    """Best-effort human name from `pactl list sinks`."""
    result = _run(["pactl", "list", "sinks"])
    if result.returncode != 0:
        return sink_name
    blocks = result.stdout.split("Sink #")
    for block in blocks:
        if f"Name: {sink_name}" not in block and f"Name: {sink_name}\n" not in block:
            # Exact line match
            if not re.search(rf"(?m)^Name:\s*{re.escape(sink_name)}\s*$", block):
                continue
        desc_m = re.search(r"(?m)^Description:\s*(.+)$", block)
        if desc_m:
            return desc_m.group(1).strip()
    return sink_name


def list_bluetooth_sinks() -> list[dict]:
    """List connected/available BlueZ A2DP (or similar) sinks for the audio picker."""
    devices: list[dict] = []
    if not pulse_available():
        return devices

    for name, state in _pactl_short_sinks():
        if not BLUEZ_SINK_RE.search(name):
            continue
        desc = _sink_description(name)
        label = f"Bluetooth — {desc}"
        if state and state.upper() not in ("RUNNING", "IDLE", "SUSPENDED"):
            label = f"{label} ({state})"
        devices.append({
            "id": pulse_device_id(name),
            "kind": "bluetooth",
            "name": desc,
            "pcm_name": name,
            "label": label,
            "sample_rate": 44100,
            "sink": name,
            "state": state,
        })
    return devices


def set_pulse_sink_volume(sink_name: str, volume: int) -> tuple[bool, str]:
    """Set Pulse/PipeWire sink volume (0–100%)."""
    if not pulse_available():
        return False, "pactl non disponibile"
    sink = sink_name.strip()
    if not sink:
        return False, "Sink Pulse non specificato"
    pct = max(0, min(100, int(volume)))
    result = _run(["pactl", "set-sink-volume", sink, f"{pct}%"])
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "set-sink-volume fallito").strip()
        return False, err
    # Unmute if muted
    _run(["pactl", "set-sink-mute", sink, "0"])
    detail = f"pulse:{sink}={pct}%"
    log.info("Volume Pulse: %s", detail)
    return True, detail


def ensure_pulse_sink_ready(sink_name: str) -> tuple[bool, str]:
    """Verify sink exists; optionally set as default for the session."""
    if not pulse_available():
        return False, "pactl non disponibile (installa pipewire-pulse o pulseaudio-utils)"
    sink = sink_name.strip()
    names = {n for n, _ in _pactl_short_sinks()}
    if sink not in names:
        return False, f"Sink Bluetooth «{sink}» non trovato — accoppia le cuffie/casse e riprova"
    _run(["pactl", "set-default-sink", sink])
    return True, "ok"


# --- Pairing (bluetoothctl) — Pi OS Lite senza GUI ---

BT_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
BT_SCAN_LOCK = Path(os.environ.get("TABLOZA_BT_SCAN_LOCK", "/run/tabloza/bt-scanning"))
BT_SCAN_SECONDS = int(os.environ.get("TABLOZA_BT_SCAN_SECONDS", "12"))


def bluetoothctl_available() -> bool:
    return shutil.which("bluetoothctl") is not None


def _btctl(*args: str, timeout: float = 20) -> subprocess.CompletedProcess:
    return _run(["bluetoothctl", *args], timeout=timeout)


def _normalize_mac(address: str) -> str:
    mac = (address or "").strip().upper()
    if not BT_MAC_RE.match(mac):
        raise ValueError("Indirizzo Bluetooth non valido")
    return mac


def ensure_bluetooth_adapter() -> tuple[bool, str]:
    """Power on adapter and register a simple agent for headless pairing."""
    if not bluetoothctl_available():
        return False, "bluetoothctl non disponibile — installa bluez"
    _run(["rfkill", "unblock", "bluetooth"], timeout=5)
    steps = [
        ("power", ["power", "on"]),
        ("agent", ["agent", "NoInputNoOutput"]),
        ("default-agent", ["default-agent"]),
        ("pairable", ["pairable", "on"]),
        ("discoverable", ["discoverable", "off"]),
    ]
    errors: list[str] = []
    for name, args in steps:
        result = _btctl(*args, timeout=10)
        out = ((result.stdout or "") + (result.stderr or "")).strip()
        if result.returncode != 0 and name in ("power", "agent"):
            errors.append(f"{name}: {out or 'fallito'}")
    # Adapter presence
    show = _btctl("show", timeout=8)
    text = (show.stdout or "") + (show.stderr or "")
    if "No default controller" in text or "No controller" in text:
        return False, "Nessun adattatore Bluetooth trovato sul Pi"
    if "Powered: no" in text:
        return False, "Bluetooth spento — riprova o verifica rfkill"
    if errors and "Powered: yes" not in text:
        return False, "; ".join(errors)
    return True, "ok"


def _parse_devices_output(text: str) -> list[dict]:
    devices: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        # Device AA:BB:CC:DD:EE:FF Name…
        m = re.match(r"^Device\s+(([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s*(.*)$", line)
        if not m:
            continue
        address = m.group(1).upper()
        if address in seen:
            continue
        seen.add(address)
        name = (m.group(3) or "").strip() or address
        devices.append({"address": address, "name": name})
    return devices


def _device_info(address: str) -> dict:
    result = _btctl("info", address, timeout=10)
    text = result.stdout or ""
    info = {
        "address": address.upper(),
        "name": address.upper(),
        "paired": "Paired: yes" in text,
        "trusted": "Trusted: yes" in text,
        "connected": "Connected: yes" in text,
        "icon": "",
    }
    name_m = re.search(r"(?m)^\s*Name:\s*(.+)$", text)
    if name_m:
        info["name"] = name_m.group(1).strip()
    alias_m = re.search(r"(?m)^\s*Alias:\s*(.+)$", text)
    if alias_m and info["name"] == address.upper():
        info["name"] = alias_m.group(1).strip()
    icon_m = re.search(r"(?m)^\s*Icon:\s*(.+)$", text)
    if icon_m:
        info["icon"] = icon_m.group(1).strip()
    return info


def list_bluetooth_devices(*, known_only: bool = False) -> list[dict]:
    """Paired/known devices; if not known_only, also recently discovered."""
    if not bluetoothctl_available():
        return []
    result = _btctl("devices", timeout=10)
    devices = _parse_devices_output(result.stdout or "")
    enriched: list[dict] = []
    for dev in devices:
        info = _device_info(dev["address"])
        if known_only and not (info["paired"] or info["trusted"] or info["connected"]):
            continue
        enriched.append({**dev, **info})
    enriched.sort(key=lambda d: (not d.get("connected"), not d.get("paired"), d.get("name") or ""))
    return enriched


def _remove_unpaired_discovered_devices() -> int:
    """Drop cached discoveries so a new scan starts from an empty list (keeps paired)."""
    removed = 0
    for dev in list_bluetooth_devices(known_only=False):
        if dev.get("paired") or dev.get("trusted") or dev.get("connected"):
            continue
        address = dev.get("address") or ""
        if not address:
            continue
        result = _btctl("remove", address, timeout=10)
        out = ((result.stdout or "") + (result.stderr or "")).strip()
        if result.returncode == 0 or "removed" in out.lower():
            removed += 1
    if removed:
        log.info("Rimossi %d dispositivi Bluetooth non accoppiati prima della scansione", removed)
    return removed


def scan_bluetooth_devices(duration_sec: int | None = None) -> tuple[list[dict], str | None]:
    """Scan for nearby devices (headless). Leaves adapter powered on."""
    ok, detail = ensure_bluetooth_adapter()
    if not ok:
        return [], detail

    seconds = max(5, min(30, int(duration_sec or BT_SCAN_SECONDS)))
    BT_SCAN_LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        BT_SCAN_LOCK.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass

    # Reset lista: togli discovery vecchie (i paired restano)
    _remove_unpaired_discovered_devices()

    log.info("Scansione Bluetooth (%ds)…", seconds)
    # Su BlueZ recenti `scan on` esce subito e ferma la discovery: usare --timeout
    scan = _run(
        ["bluetoothctl", f"--timeout={seconds}", "scan", "on"],
        timeout=seconds + 15,
    )
    scan_out = ((scan.stdout or "") + (scan.stderr or "")).strip()
    if scan.returncode not in (0, 124) and "Discovery started" not in scan_out:
        log.warning("bluetoothctl scan: %s", scan_out or f"exit {scan.returncode}")
    try:
        BT_SCAN_LOCK.unlink(missing_ok=True)
    except OSError:
        pass

    devices = list_bluetooth_devices(known_only=False)
    log.info("Bluetooth: trovati %d dispositivi", len(devices))
    return devices, None


def _btctl_bg_scan_start() -> subprocess.Popen | None:
    """Keep discovery running in background during pair/connect."""
    try:
        return subprocess.Popen(
            ["bluetoothctl", "scan", "on"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        log.warning("Impossibile avviare scan BT in background: %s", exc)
        return None


def _btctl_bg_scan_stop(proc: subprocess.Popen | None) -> None:
    _btctl("scan", "off", timeout=8)
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass


def _wait_device_available(mac: str, timeout_sec: float = 20.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        info_txt = _btctl("info", mac, timeout=5)
        text = (info_txt.stdout or "") + (info_txt.stderr or "")
        if "not available" not in text.lower() and (
            f"Device {mac}" in text or "Name:" in text or "Alias:" in text
        ):
            return True
        devices = _parse_devices_output(_btctl("devices", timeout=5).stdout or "")
        if any(d["address"] == mac for d in devices):
            return True
        time.sleep(1.0)
    return False


def pair_bluetooth_device(address: str) -> tuple[bool, str]:
    """Pair + trust + connect for A2DP headphones/speakers."""
    try:
        mac = _normalize_mac(address)
    except ValueError as exc:
        return False, str(exc)

    ok, detail = ensure_bluetooth_adapter()
    if not ok:
        return False, detail

    log.info("Pairing Bluetooth %s…", mac)
    scan_proc = _btctl_bg_scan_start()
    try:
        # Auricolari LE (es. OPPO Enco) spariscono subito: tieni la discovery attiva
        time.sleep(2.0)
        if not _wait_device_available(mac, timeout_sec=18.0):
            return False, (
                "Dispositivo non raggiungibile — rimetti le cuffie in modalità pairing "
                "e rilancia la scansione, poi Accoppia subito"
            )

        info = _device_info(mac)
        if info.get("paired") and info.get("connected"):
            return True, f"Già collegato a {info.get('name', mac)}"

        if info.get("paired") and not info.get("connected"):
            conn_out = _connect_with_retry(mac)
            info = _device_info(mac)
            if info.get("connected"):
                return True, f"Collegato a {info.get('name', mac)}"
            return False, _friendly_connect_error(conn_out)

        pair = _btctl("pair", mac, timeout=90)
        pair_out = ((pair.stdout or "") + (pair.stderr or "")).strip()
        pair_ok = (
            pair.returncode == 0
            or "Pairing successful" in pair_out
            or "AlreadyExists" in pair_out
            or "already paired" in pair_out.lower()
        )
        if not pair_ok and (
            "Failed" in pair_out
            or "Authentication" in pair_out
            or "not available" in pair_out.lower()
            or "No agent" in pair_out
        ):
            if "not available" in pair_out.lower():
                return False, (
                    "Dispositivo sparito durante il pairing — tieni le cuffie "
                    "in modalità pairing vicino al Pi e riprova subito dopo la scansione"
                )
            return False, pair_out or "Pairing fallito"

        time.sleep(1.5)
        info = _device_info(mac)
        if not info.get("paired") and not pair_ok:
            return False, (
                pair_out
                or "Pairing non completato — conferma la modalità pairing sulle cuffie e riprova"
            )

        _btctl("trust", mac, timeout=15)
        conn_out = _connect_with_retry(mac, attempts=3, timeout=60)

        info = _device_info(mac)
        if info.get("connected"):
            name = info.get("name") or mac
            for _ in range(12):
                if list_bluetooth_sinks():
                    break
                time.sleep(0.5)
            if list_bluetooth_sinks():
                return True, f"Accoppiato e collegato: {name} (audio pronto)"
            return True, (
                f"Accoppiato e collegato: {name} — se non compare in Uscita audio, "
                "premi Aggiorna elenco tra qualche secondo"
            )

        return False, _friendly_connect_error(conn_out or pair_out)
    finally:
        _btctl_bg_scan_stop(scan_proc)


def _connect_with_retry(mac: str, attempts: int = 2, timeout: int = 45) -> str:
    """bluetoothctl connect; retry su refused (cuffie ancora in setup A2DP)."""
    last = ""
    for i in range(max(1, attempts)):
        result = _btctl("connect", mac, timeout=timeout)
        last = ((result.stdout or "") + (result.stderr or "")).strip()
        time.sleep(2.0)
        if _device_info(mac).get("connected") or "Connection successful" in last:
            return last or "Connection successful"
        if "profile-unavailable" in last.lower():
            break
        if i + 1 < attempts:
            time.sleep(1.5)
    return last


def _friendly_connect_error(raw: str) -> str:
    text = (raw or "").strip()
    low = text.lower()
    if "profile-unavailable" in low:
        return (
            "Profilo audio A2DP non disponibile sul Pi (WirePlumber/BlueZ). "
            "Esegui sudo tabloza-update oppure: "
            "systemctl --user restart wireplumber "
            "poi verifica: bluetoothctl show | grep 'Audio Source'"
        )
    if "connection refused" in low or "br-connection-refused" in low:
        return (
            "Connessione rifiutata dalle cuffie — disconnettile dal telefono, "
            "riaprirle vicino al Pi e riprova Accoppia/Collega"
        )
    if "not available" in low:
        return (
            "Cuffie non più in range/pairing durante la connessione — "
            "riapri la custodia in modalità pairing e riprova"
        )
    return text or "Connessione fallita"


def connect_bluetooth_device(address: str) -> tuple[bool, str]:
    try:
        mac = _normalize_mac(address)
    except ValueError as exc:
        return False, str(exc)
    ok, detail = ensure_bluetooth_adapter()
    if not ok:
        return False, detail
    scan_proc = _btctl_bg_scan_start()
    try:
        time.sleep(1.0)
        out = _connect_with_retry(mac)
        info = _device_info(mac)
        if info.get("connected"):
            return True, f"Collegato a {info.get('name', mac)}"
        return False, _friendly_connect_error(out)
    finally:
        _btctl_bg_scan_stop(scan_proc)


def disconnect_bluetooth_device(address: str) -> tuple[bool, str]:
    try:
        mac = _normalize_mac(address)
    except ValueError as exc:
        return False, str(exc)
    result = _btctl("disconnect", mac, timeout=20)
    out = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode == 0 or "Successful" in out:
        return True, "Dispositivo scollegato"
    return False, out or "Disconnessione fallita"


def remove_bluetooth_device(address: str) -> tuple[bool, str]:
    try:
        mac = _normalize_mac(address)
    except ValueError as exc:
        return False, str(exc)
    _btctl("disconnect", mac, timeout=15)
    result = _btctl("remove", mac, timeout=20)
    out = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode == 0 or "Device has been removed" in out:
        return True, "Dispositivo rimosso"
    return False, out or "Rimozione fallita"


def bluetooth_status() -> dict:
    ctl = bluetoothctl_available()
    pulse = pulse_available()
    adapter_ok = False
    adapter_detail = "bluetoothctl assente"
    if ctl:
        show = _btctl("show", timeout=8)
        text = (show.stdout or "") + (show.stderr or "")
        if "No default controller" in text or "No controller" in text:
            adapter_detail = "Nessun adattatore Bluetooth trovato sul Pi"
        elif "Powered: yes" in text:
            adapter_ok = True
            adapter_detail = "ok"
        else:
            adapter_detail = "Bluetooth spento — avvia una scansione per accenderlo"
    return {
        "bluetoothctl": ctl,
        "pulse": pulse,
        "adapter_ok": adapter_ok,
        "adapter_detail": adapter_detail,
        "scanning": BT_SCAN_LOCK.is_file(),
        "sinks": list_bluetooth_sinks() if pulse else [],
        "devices": list_bluetooth_devices(known_only=True) if ctl else [],
    }

"""WiFi scan/connect helpers via NetworkManager."""

import re
import subprocess
import time

from event_log import log_event

HOTSPOT_CONN = "tabloza-hotspot"
WLAN_IFACE = "wlan0"


def _run(cmd: list[str], timeout: float = 15) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def parse_nmcli_terse_fields(line: str) -> list[str]:
    """Split nmcli -t line respecting \\: escapes."""
    fields: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line) and line[i + 1] == ":":
            current.append(":")
            i += 2
        elif line[i] == ":":
            fields.append("".join(current))
            current = []
            i += 1
        else:
            current.append(line[i])
            i += 1
    fields.append("".join(current))
    return fields


def _wlan_device_present() -> bool:
    result = _run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"], timeout=5)
    for line in result.stdout.splitlines():
        fields = parse_nmcli_terse_fields(line.strip())
        if len(fields) >= 2 and fields[0] == WLAN_IFACE and fields[1] == "wifi":
            return True
    return False


def _active_wifi_connection() -> str:
    result = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"], timeout=5)
    for line in result.stdout.splitlines():
        fields = parse_nmcli_terse_fields(line.strip())
        if len(fields) >= 2 and fields[1] == "802-11-wireless":
            return fields[0]
    return ""


def prepare_wifi_scan() -> tuple[bool, str]:
    """Switch wlan0 out of AP mode so scans can run."""
    if not _wlan_device_present():
        msg = f"Interfaccia {WLAN_IFACE} non gestita da NetworkManager"
        log_event("wifi", msg, "error")
        return False, msg

    _run(["nmcli", "radio", "wifi", "on"], timeout=5)
    active = _active_wifi_connection()
    if active == HOTSPOT_CONN:
        log_event("wifi", "Disattivo hotspot per permettere la scansione…")
        down = _run(["nmcli", "connection", "down", HOTSPOT_CONN], timeout=15)
        if down.returncode != 0:
            err = (down.stderr or down.stdout or "down fallito").strip()
            log_event("wifi", f"Impossibile disattivare hotspot: {err}", "error")
            return False, f"Hotspot attivo — impossibile scansionare: {err}"
        time.sleep(2.0)
    elif active:
        log_event("wifi", f"WiFi già connesso a «{active}» — scansione in corso")
    return True, "ok"


def scan_wifi_networks() -> tuple[list[dict], str | None]:
    """Return visible WiFi networks sorted by signal strength."""
    ok, detail = prepare_wifi_scan()
    if not ok:
        return [], detail

    log_event("wifi", "Scansione reti WiFi…")
    result = _run(
        ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"],
        timeout=25,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "nmcli fallito").strip()
        log_event("wifi", f"Scan fallito: {err}", "error")
        return [], err

    networks: list[dict] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = parse_nmcli_terse_fields(line)
        if len(fields) < 2:
            continue
        ssid = fields[0].strip()
        if not ssid or ssid == "--":
            continue
        if ssid in seen:
            continue
        seen.add(ssid)
        signal_raw = fields[1].strip()
        security = fields[2].strip() if len(fields) > 2 else ""
        networks.append({
            "ssid": ssid,
            "signal": int(signal_raw) if signal_raw.isdigit() else 0,
            "security": security,
        })

    networks.sort(key=lambda n: n["signal"], reverse=True)
    log_event("wifi", f"Trovate {len(networks)} reti")
    return networks, None


def _safe_conn_name(ssid: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", ssid.strip())[:20] or "wifi"
    return f"tabloza-wifi-{safe}"


def _delete_wifi_profiles_for_ssid(ssid: str) -> None:
    """Remove saved NM profiles for this SSID so connect does not reuse stale secrets."""
    result = _run(
        ["nmcli", "-t", "-f", "NAME,802-11-wireless.ssid", "connection", "show"],
        timeout=10,
    )
    for line in result.stdout.splitlines():
        fields = parse_nmcli_terse_fields(line.strip())
        if len(fields) >= 2 and fields[1] == ssid and fields[0] != HOTSPOT_CONN:
            _run(["nmcli", "connection", "delete", fields[0]], timeout=10)


def _ssid_requires_password(security: str) -> bool:
    sec = (security or "").strip()
    return bool(sec and sec != "--")


def connect_wifi_network(
    ssid: str,
    password: str = "",
    security: str = "",
) -> tuple[bool, str | None]:
    """Connect wlan0 to an infrastructure WiFi network (stores credentials in NM)."""
    ssid = ssid.strip()
    if not ssid:
        return False, "SSID richiesto"

    if _ssid_requires_password(security) and not password:
        return False, "Password WiFi richiesta per questa rete"

    ok, detail = prepare_wifi_scan()
    if not ok:
        return False, detail

    log_event("wifi", f"Connessione a «{ssid}»…")
    _run(["nmcli", "connection", "down", HOTSPOT_CONN], timeout=15)

    conn_name = _safe_conn_name(ssid)
    _delete_wifi_profiles_for_ssid(ssid)
    _run(["nmcli", "connection", "delete", conn_name], timeout=10)

    add_cmd = [
        "nmcli", "connection", "add", "type", "wifi",
        "con-name", conn_name,
        "ifname", WLAN_IFACE,
        "ssid", ssid,
    ]
    if password:
        add_cmd += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]
    else:
        add_cmd += ["wifi-sec.key-mgmt", "none"]

    add_result = _run(add_cmd, timeout=30)
    if add_result.returncode != 0:
        err = (add_result.stderr or add_result.stdout or "creazione profilo fallita").strip()
        log_event("wifi", f"Connessione fallita: {err}", "error")
        return False, err

    result = _run(["nmcli", "--wait", "45", "connection", "up", conn_name], timeout=60)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "connessione fallita").strip()
        log_event("wifi", f"Connessione fallita: {err}", "error")
        return False, err

    _run([
        "nmcli", "connection", "modify", conn_name,
        "connection.autoconnect", "yes",
        "connection.autoconnect-priority", "100",
    ], timeout=10)
    _run(["nmcli", "connection", "down", HOTSPOT_CONN], timeout=10)
    log_event("wifi", f"Connesso a «{ssid}»")
    return True, None

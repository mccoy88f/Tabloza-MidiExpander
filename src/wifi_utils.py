"""WiFi scan/connect helpers via NetworkManager."""

import os
import re
import subprocess
import tempfile
import time

from event_log import log_event

HOTSPOT_CONN = "tabloza-hotspot"
WLAN_IFACE = "wlan0"
WIFI_CONNECT_LOCK = os.environ.get("TABLOZA_WIFI_CONNECT_LOCK", "/run/tabloza/wifi-connecting")
NM_WAIT_SEC = 90


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
    result = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"], timeout=10)
    for line in result.stdout.splitlines():
        fields = parse_nmcli_terse_fields(line.strip())
        if len(fields) < 2 or fields[1] != "802-11-wireless":
            continue
        name = fields[0]
        if name == HOTSPOT_CONN:
            continue
        ssid_result = _run(
            ["nmcli", "-g", "802-11-wireless.ssid", "connection", "show", name],
            timeout=5,
        )
        if ssid_result.stdout.strip() == ssid:
            _run(["nmcli", "connection", "delete", name], timeout=10)
    _run(["nmcli", "connection", "delete", _safe_conn_name(ssid)], timeout=10)


def _ssid_requires_password(security: str) -> bool:
    sec = (security or "").strip()
    return bool(sec and sec != "--")


def _wifi_key_mgmt(security: str) -> str:
    sec = (security or "").upper()
    if "WPA3" in sec or "SAE" in sec:
        return "sae"
    return "wpa-psk"


def _wifi_key_mgmt_options(security: str) -> list[str]:
    primary = _wifi_key_mgmt(security)
    if primary == "sae":
        return ["sae", "wpa-psk"]
    return ["wpa-psk"]


class _WifiConnectLock:
    def __enter__(self):
        os.makedirs(os.path.dirname(WIFI_CONNECT_LOCK), exist_ok=True)
        with open(WIFI_CONNECT_LOCK, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        return self

    def __exit__(self, *_args):
        try:
            os.unlink(WIFI_CONNECT_LOCK)
        except OSError:
            pass


def _wlan_state() -> str:
    result = _run(["nmcli", "-t", "-f", "DEVICE,STATE", "device"], timeout=5)
    for line in result.stdout.splitlines():
        fields = parse_nmcli_terse_fields(line.strip())
        if len(fields) >= 2 and fields[0] == WLAN_IFACE:
            return fields[1]
    return ""


def _ensure_wlan_client_ready() -> None:
    """Leave AP mode and wait until wlan0 can join an infrastructure network."""
    _run(["nmcli", "connection", "down", HOTSPOT_CONN], timeout=20)
    _run(["nmcli", "device", "disconnect", WLAN_IFACE], timeout=20)
    for _ in range(20):
        state = _wlan_state()
        if state in ("disconnected", "unavailable", ""):
            break
        if state == "connected":
            active = _active_wifi_connection()
            if active and active != HOTSPOT_CONN:
                return
            _run(["nmcli", "device", "disconnect", WLAN_IFACE], timeout=20)
        time.sleep(0.5)
    _run(["nmcli", "radio", "wifi", "on"], timeout=5)
    _run(["nmcli", "device", "wifi", "rescan"], timeout=15)
    time.sleep(2.0)


def _ssid_visible(ssid: str) -> bool:
    result = _run(["nmcli", "-t", "-f", "SSID", "device", "wifi", "list"], timeout=15)
    for line in result.stdout.splitlines():
        fields = parse_nmcli_terse_fields(line.strip())
        if fields and fields[0].strip() == ssid:
            return True
    return False


def _friendly_connect_error(err: str) -> str:
    low = err.lower()
    if "timeout" in low:
        return (
            "Timeout connessione (90s) — verifica password, avvicina il router "
            "e ripeti la scansione"
        )
    if "secrets were required" in low or "no secrets" in low:
        return "Password WiFi mancante o errata"
    return err


def _apply_autoconnect(conn_name: str) -> None:
    _run([
        "nmcli", "connection", "modify", conn_name,
        "connection.autoconnect", "yes",
        "connection.autoconnect-priority", "100",
    ], timeout=10)
    _run(["nmcli", "connection", "down", HOTSPOT_CONN], timeout=10)


def _connect_via_device_wifi(
    ssid: str,
    password: str,
    conn_name: str,
) -> subprocess.CompletedProcess:
    cmd = [
        "nmcli", "--wait", str(NM_WAIT_SEC),
        "device", "wifi", "connect", ssid,
        "ifname", WLAN_IFACE,
        "name", conn_name,
    ]
    if password:
        cmd += ["password", password]
    return _run(cmd, timeout=NM_WAIT_SEC + 15)


def _connect_via_profile(
    ssid: str,
    password: str,
    security: str,
    conn_name: str,
    key_mgmt: str,
) -> subprocess.CompletedProcess | None:
    _delete_wifi_profiles_for_ssid(ssid)
    add_cmd = [
        "nmcli", "connection", "add", "type", "wifi",
        "con-name", conn_name,
        "ifname", WLAN_IFACE,
        "ssid", ssid,
        "802-11-wireless.mode", "infrastructure",
        "wifi-sec.key-mgmt", key_mgmt,
    ]
    add_result = _run(add_cmd, timeout=30)
    if add_result.returncode != 0:
        return add_result

    if password:
        mod_result = _run([
            "nmcli", "connection", "modify", conn_name,
            "wifi-sec.key-mgmt", key_mgmt,
            "wifi-sec.psk", password,
        ], timeout=10)
        if mod_result.returncode != 0:
            return mod_result

    return _connection_up(conn_name, password=password)


def _write_nm_passwd_file(password: str) -> str:
    """Temp file for nmcli connection up passwd-file (802-11-wireless-security.psk)."""
    fd, path = tempfile.mkstemp(prefix="tabloza-nm-passwd-")
    with os.fdopen(fd, "w") as fh:
        fh.write(f"802-11-wireless-security.psk:{password}\n")
    os.chmod(path, 0o600)
    return path


def _connection_up(conn_name: str, password: str = "") -> subprocess.CompletedProcess:
    up_cmd = ["nmcli", "--wait", str(NM_WAIT_SEC), "connection", "up", conn_name]
    passwd_path = None
    if password:
        passwd_path = _write_nm_passwd_file(password)
        up_cmd += ["passwd-file", passwd_path]
    try:
        return _run(up_cmd, timeout=NM_WAIT_SEC + 15)
    finally:
        if passwd_path:
            try:
                os.unlink(passwd_path)
            except OSError:
                pass


def _eth_connected() -> bool:
    result = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"], timeout=5)
    for line in result.stdout.splitlines():
        fields = parse_nmcli_terse_fields(line.strip())
        if len(fields) >= 3 and fields[1] == "ethernet" and fields[2] == "connected":
            return True
    return False


def get_network_status() -> dict:
    """Report ethernet/WiFi state for dashboard."""
    from network_utils import is_lan_direct_active, LAN_DIRECT_IP

    eth = _eth_connected()
    lan_direct = is_lan_direct_active()
    wlan_mode = "disconnected"
    wifi_name = ""

    wlan_state = _wlan_state()
    if wlan_state == "connected":
        wifi_name = _active_wifi_connection()
        if wifi_name == HOTSPOT_CONN:
            wlan_mode = "hotspot"
        elif wifi_name:
            wlan_mode = "client"

    if lan_direct:
        network_mode = "lan_direct"
    elif eth and wlan_mode == "client":
        network_mode = "lan_wifi"
    elif eth:
        network_mode = "ethernet"
    elif wlan_mode == "hotspot":
        network_mode = "hotspot"
    elif wlan_mode == "client":
        network_mode = "client"
    else:
        network_mode = "offline"

    return {
        "network_mode": network_mode,
        "ethernet_connected": eth or lan_direct,
        "eth_on_router": network_mode in ("ethernet", "lan_wifi"),
        "lan_direct_active": lan_direct,
        "lan_direct_ip": LAN_DIRECT_IP if lan_direct else "",
        "hotspot_active": wlan_mode == "hotspot",
        "wifi_client_active": wlan_mode == "client",
        "wlan_mode": wlan_mode,
        "wifi_connection": wifi_name,
    }


def start_hotspot() -> tuple[bool, str | None]:
    """Start provisioning AP (optional when Pi is on Ethernet)."""
    if not _wlan_device_present():
        return False, f"Interfaccia {WLAN_IFACE} non disponibile"

    with _WifiConnectLock():
        log_event("wifi", "Avvio hotspot provisioning…")
        _run(["nmcli", "device", "disconnect", WLAN_IFACE], timeout=15)
        result = _run(["nmcli", "connection", "up", HOTSPOT_CONN], timeout=30)
        if result.returncode != 0:
            result = _run([
                "nmcli", "device", "wifi", "hotspot",
                "ifname", WLAN_IFACE,
                "ssid", "Tabloza-MidiExpander",
                "password", "",
            ], timeout=30)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "hotspot fallito").strip()
            log_event("wifi", f"Hotspot fallito: {err}", "error")
            return False, err
        log_event("wifi", "Hotspot Tabloza-MidiExpander attivo")
        return True, None


def stop_hotspot() -> tuple[bool, str | None]:
    """Stop AP and leave wlan ready for client scan/connect."""
    with _WifiConnectLock():
        result = _run(["nmcli", "connection", "down", HOTSPOT_CONN], timeout=15)
        _run(["nmcli", "device", "disconnect", WLAN_IFACE], timeout=15)
        if result.returncode != 0 and _wlan_state() == "connected":
            active = _active_wifi_connection()
            if active == HOTSPOT_CONN:
                err = (result.stderr or result.stdout or "spegnimento hotspot fallito").strip()
                return False, err
        log_event("wifi", "Hotspot disattivato")
        return True, None


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

    use_psk = bool(password) or _ssid_requires_password(security)

    with _WifiConnectLock():
        ok, detail = prepare_wifi_scan()
        if not ok:
            return False, detail

        log_event("wifi", f"Connessione a «{ssid}»…")
        _ensure_wlan_client_ready()

        if not _ssid_visible(ssid):
            msg = f"Rete «{ssid}» non visibile — ripeti la scansione e riprova"
            log_event("wifi", msg, "error")
            return False, msg

        conn_name = _safe_conn_name(ssid)
        _delete_wifi_profiles_for_ssid(ssid)

        if use_psk or password:
            result = _connect_via_device_wifi(ssid, password, conn_name)
            if result.returncode == 0:
                _apply_autoconnect(conn_name)
                log_event("wifi", f"Connesso a «{ssid}»")
                return True, None
            err = (result.stderr or result.stdout or "connessione fallita").strip()
            log_event("wifi", f"device wifi connect fallito: {err}")

            for key_mgmt in _wifi_key_mgmt_options(security):
                log_event("wifi", f"Tentativo profilo NM ({key_mgmt})…")
                result = _connect_via_profile(ssid, password, security, conn_name, key_mgmt)
                if result is not None and result.returncode == 0:
                    _apply_autoconnect(conn_name)
                    log_event("wifi", f"Connesso a «{ssid}»")
                    return True, None
                if result is not None:
                    err = (result.stderr or result.stdout or err).strip()

            log_event("wifi", f"Connessione fallita: {err}", "error")
            return False, _friendly_connect_error(err)

        result = _connect_via_profile(ssid, "", security, conn_name, "none")
        if result is not None and result.returncode == 0:
            _apply_autoconnect(conn_name)
            log_event("wifi", f"Connesso a «{ssid}»")
            return True, None

        err = "connessione fallita"
        if result is not None:
            err = (result.stderr or result.stdout or err).strip()
        log_event("wifi", f"Connessione fallita: {err}", "error")
        return False, _friendly_connect_error(err)

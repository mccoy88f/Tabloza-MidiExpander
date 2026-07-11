"""Tabloza — Ethernet link diretto (Pi come router/DHCP sul cavo)."""

import os
import time
from pathlib import Path

from event_log import log_event
from wifi_utils import parse_nmcli_terse_fields, _run

LAN_DIRECT_CONN = "tabloza-lan-direct"
LAN_DIRECT_IP = "192.168.5.1"
LAN_DIRECT_CIDR = f"{LAN_DIRECT_IP}/24"
ETH_DHCP_GRACE_SEC = int(os.environ.get("TABLOZA_ETH_DHCP_GRACE", "25"))
ETH_CARRIER_SINCE_FILE = os.environ.get(
    "TABLOZA_ETH_CARRIER_SINCE", "/run/tabloza/eth-carrier-since",
)


def get_primary_ethernet_device() -> str | None:
    result = _run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"], timeout=5)
    for line in result.stdout.splitlines():
        fields = parse_nmcli_terse_fields(line.strip())
        if len(fields) >= 2 and fields[1] == "ethernet":
            return fields[0]
    return None


def is_lan_direct_active() -> bool:
    result = _run(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"], timeout=5)
    return LAN_DIRECT_CONN in result.stdout.splitlines()


def _ethernet_carrier_up(device: str) -> bool:
    result = _run(["nmcli", "-g", "WIRED-PROPERTIES.CARRIER", "device", "show", device], timeout=5)
    return result.stdout.strip().lower() in ("on", "true", "1", "yes")


def _eth_ipv4_addresses(device: str) -> list[str]:
    result = _run(["nmcli", "-g", "IP4.ADDRESS", "device", "show", device], timeout=5)
    addrs: list[str] = []
    for line in result.stdout.splitlines():
        raw = line.strip()
        if not raw or raw == "--":
            continue
        addrs.append(raw.split("/")[0])
    return addrs


def get_usable_ipv4(device: str) -> str:
    """First non link-local IPv4 on a NetworkManager device."""
    for ip in _eth_ipv4_addresses(device):
        if ip.startswith("169.254."):
            continue
        return ip
    return ""


def has_usable_eth_ip(device: str) -> bool:
    """True if eth has a non link-local IPv4 (router DHCP or lan-direct 192.168.5.1)."""
    for ip in _eth_ipv4_addresses(device):
        if ip.startswith("169.254."):
            continue
        return True
    return False


def _is_router_dhcp_ip(device: str) -> bool:
    for ip in _eth_ipv4_addresses(device):
        if ip.startswith("169.254.") or ip.startswith("192.168.5."):
            continue
        return True
    return False


def _read_carrier_since() -> float | None:
    try:
        if os.path.isfile(ETH_CARRIER_SINCE_FILE):
            return float(Path(ETH_CARRIER_SINCE_FILE).read_text().strip())
    except (OSError, ValueError):
        pass
    return None


def _write_carrier_since(when: float) -> None:
    os.makedirs(os.path.dirname(ETH_CARRIER_SINCE_FILE), exist_ok=True)
    with open(ETH_CARRIER_SINCE_FILE, "w", encoding="utf-8") as fh:
        fh.write(str(when))


def _clear_carrier_since() -> None:
    try:
        os.unlink(ETH_CARRIER_SINCE_FILE)
    except OSError:
        pass


def _ensure_dhcp_on_device(device: str) -> None:
    if is_lan_direct_active():
        return
    _run(["nmcli", "connection", "down", LAN_DIRECT_CONN], timeout=10)
    _run(["nmcli", "device", "connect", device], timeout=30)


def start_lan_direct() -> tuple[bool, str | None]:
    """Shared IPv4 on eth: DHCP + NAT verso WiFi/upstream (cavo Pi ↔ Mac/PC)."""
    device = get_primary_ethernet_device()
    if not device:
        return False, "Interfaccia Ethernet non trovata"

    log_event("network", f"Avvio link LAN diretto su {device} ({LAN_DIRECT_IP})…")
    _run(["nmcli", "connection", "down", LAN_DIRECT_CONN], timeout=15)
    _run(["nmcli", "connection", "delete", LAN_DIRECT_CONN], timeout=10)

    add = _run([
        "nmcli", "connection", "add", "type", "ethernet",
        "con-name", LAN_DIRECT_CONN,
        "ifname", device,
        "ipv4.method", "shared",
        "ipv4.addresses", LAN_DIRECT_CIDR,
        "connection.autoconnect", "no",
        "ipv6.method", "ignore",
    ], timeout=20)
    if add.returncode != 0:
        err = (add.stderr or add.stdout or "creazione profilo fallita").strip()
        log_event("network", f"Link LAN diretto fallito: {err}", "error")
        return False, err

    up = _run(["nmcli", "--wait", "30", "connection", "up", LAN_DIRECT_CONN], timeout=40)
    if up.returncode != 0:
        err = (up.stderr or up.stdout or "attivazione fallita").strip()
        _run(["nmcli", "connection", "delete", LAN_DIRECT_CONN], timeout=10)
        log_event("network", f"Link LAN diretto fallito: {err}", "error")
        return False, err

    log_event("network", f"Link LAN diretto attivo — {LAN_DIRECT_IP} (DHCP sul cavo)")
    return True, None


def stop_lan_direct(skip_reconnect: bool = False) -> tuple[bool, str | None]:
    device = get_primary_ethernet_device()
    result = _run(["nmcli", "connection", "down", LAN_DIRECT_CONN], timeout=15)
    _run(["nmcli", "connection", "delete", LAN_DIRECT_CONN], timeout=10)
    if device and not skip_reconnect and _ethernet_carrier_up(device):
        _run(["nmcli", "device", "connect", device], timeout=30)
    if result.returncode != 0 and is_lan_direct_active():
        err = (result.stderr or result.stdout or "spegnimento fallito").strip()
        return False, err
    log_event("network", "Link LAN diretto disattivato — DHCP Ethernet ripristinato")
    return True, None


def manage_ethernet_auto() -> None:
    """Prefer normal DHCP on eth; after grace period without IP, enable router/shared mode."""
    device = get_primary_ethernet_device()
    if not device:
        _clear_carrier_since()
        return

    if not _ethernet_carrier_up(device):
        if is_lan_direct_active():
            stop_lan_direct(skip_reconnect=True)
        _clear_carrier_since()
        return

    if has_usable_eth_ip(device):
        if is_lan_direct_active() and _is_router_dhcp_ip(device):
            log_event("network", "Ethernet con IP router — termino link LAN diretto")
            stop_lan_direct()
        _clear_carrier_since()
        return

    if is_lan_direct_active():
        return

    since = _read_carrier_since()
    now = time.time()
    if since is None:
        _write_carrier_since(now)
        log_event("network", f"Cavo Ethernet rilevato — attesa DHCP ({ETH_DHCP_GRACE_SEC}s)…")
        _ensure_dhcp_on_device(device)
        return

    if now - since < ETH_DHCP_GRACE_SEC:
        return

    log_event("network", "Nessun IP DHCP — attivo modalità router su Ethernet")
    start_lan_direct()
    _clear_carrier_since()

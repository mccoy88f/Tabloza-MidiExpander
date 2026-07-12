"""Tabloza — gateway MIDI dedicato all'ingresso WebSocket da Tabloza Sing.

Separato dal gateway RTP/USB (Tabloza Buffer): buffer anti-jitter sempre attivo
perché il browser schedula localmente e non invia timestamp di rete.
"""

from __future__ import annotations

import logging
import threading

from midi_jitter_buffer import MidiGateway

log = logging.getLogger("tabloza.midi.ws_buffer")

WS_BUFFER_PORT_NAME = "Tabloza Sing WS"
WS_BUFFER_CLIENT_MARKERS = ("tabloza sing ws",)

_ws_gateway: MidiGateway | None = None
_ws_gateway_lock = threading.Lock()


def _is_ws_buffer_input_port(port: dict) -> bool:
    name = port.get("name", "").lower().strip()
    client = port.get("client", "").lower()
    if name == WS_BUFFER_PORT_NAME.lower() or WS_BUFFER_PORT_NAME.lower() in name:
        return True
    if any(marker in client for marker in WS_BUFFER_CLIENT_MARKERS):
        return True
    return WS_BUFFER_PORT_NAME.lower() in client


def ensure_ws_midi_gateway(buffer_ms: int, *, sysex_auto: bool = True) -> bool:
    """Start or update the Sing WebSocket MIDI gateway."""
    global _ws_gateway
    ms = max(0, buffer_ms)
    with _ws_gateway_lock:
        if (
            _ws_gateway
            and _ws_gateway.active
            and _ws_gateway.buffer_ms == ms
            and _ws_gateway.sysex_auto == sysex_auto
        ):
            return True
        if _ws_gateway:
            _ws_gateway.stop()
        _ws_gateway = MidiGateway(ms, sysex_auto=sysex_auto, port_name=WS_BUFFER_PORT_NAME)
        if _ws_gateway.start():
            log.info(
                "Gateway WS Sing attivo (buffer=%sms, sysex=%s, porta=%s)",
                ms,
                sysex_auto,
                _ws_gateway.input_port_address or "—",
            )
            return True
        log.error("Gateway WS Sing non avviato")
        _ws_gateway = None
        return False


def stop_ws_midi_gateway() -> None:
    global _ws_gateway
    with _ws_gateway_lock:
        if _ws_gateway:
            _ws_gateway.stop()
            _ws_gateway = None


def ws_gateway_active() -> bool:
    with _ws_gateway_lock:
        return bool(_ws_gateway and _ws_gateway.active)


def reconnect_ws_gateway_output() -> bool:
    with _ws_gateway_lock:
        if _ws_gateway and _ws_gateway.active:
            return _ws_gateway.reconnect_output()
        return False


def get_ws_buffer_input_port() -> dict | None:
    """ALSA input for routing Tabloza Sing WS source into the WS gateway."""
    with _ws_gateway_lock:
        cached = _ws_gateway.input_port_address if _ws_gateway and _ws_gateway.active else None
    if cached:
        return {
            "client": WS_BUFFER_PORT_NAME,
            "name": WS_BUFFER_PORT_NAME,
            "address": cached,
        }
    from midi_utils import get_input_ports, get_output_ports, orchestrator_running

    if orchestrator_running():
        for port in get_input_ports() + get_output_ports():
            if _is_ws_buffer_input_port(port):
                return port
    return None


def ws_gateway_status() -> dict:
    from midi_config import get_ws_jitter_buffer_ms, is_ws_jitter_buffer_enabled, merge_midi_config
    from midi_sysex_mode import get_runtime_bank_select
    from midi_utils import orchestrator_running
    from tabloza_common import load_config

    with _ws_gateway_lock:
        local_active = bool(_ws_gateway and _ws_gateway.active)
        ms = _ws_gateway.buffer_ms if _ws_gateway else 0
        sysex_auto = _ws_gateway.sysex_auto if _ws_gateway else False
    port = get_ws_buffer_input_port()
    alsa_active = port is not None and orchestrator_running()
    active = local_active or alsa_active
    if not local_active and alsa_active:
        cfg = load_config()
        midi = merge_midi_config(cfg.get("midi") if isinstance(cfg.get("midi"), dict) else None)
        ms = get_ws_jitter_buffer_ms(cfg) if is_ws_jitter_buffer_enabled(cfg) else 0
        sysex_auto = midi["sysex_bank_auto"]
    return {
        "active": active,
        "buffer_ms": ms if active else 0,
        "sysex_auto": sysex_auto,
        "runtime_bank_select": get_runtime_bank_select(),
        "input_port": port,
        "port_name": WS_BUFFER_PORT_NAME,
    }

#!/usr/bin/env python3
"""Tabloza MidiExpander — WebSocket MIDI server (protocollo JZZ-midi-WS).

Espone la porta output «Tabloza Sing» verso browser Tabloza Sing; i byte MIDI
arrivano su una porta ALSA virtuale instradata dal orchestrator verso Tabloza Sing WS.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import threading
from pathlib import Path

log = logging.getLogger("tabloza.midi.ws")

# Nome vista dal client JZZ.WS (deve coincidere con Tabloza Sing frontend).
JZZ_OUTPUT_NAME = "Tabloza Sing"
# Porta ALSA virtuale (sorgente verso il gateway WS).
WS_ALSA_SOURCE_NAME = "Tabloza Sing"
DEFAULT_WS_PORT = 8765

_midi_out = None
_midi_lock = threading.Lock()
_clients: set[object] = set()
_stop = threading.Event()


def _ws_port() -> int:
    raw = os.environ.get("TABLOZA_MIDI_WS_PORT", str(DEFAULT_WS_PORT))
    try:
        port = int(raw)
    except ValueError:
        port = DEFAULT_WS_PORT
    return max(1, min(65535, port))


def _info_payload() -> str:
    return json.dumps({"info": {"inputs": [], "outputs": [JZZ_OUTPUT_NAME]}})


def _init_midi_out() -> bool:
    global _midi_out
    from rtmidi_compat import is_usable_python_rtmidi, make_midi_out, rtmidi_diagnostic

    if not is_usable_python_rtmidi():
        log.error("python-rtmidi non disponibile — %s", rtmidi_diagnostic())
        return False
    with _midi_lock:
        if _midi_out is not None:
            return True
        try:
            out = make_midi_out()
            out.open_virtual_port(WS_ALSA_SOURCE_NAME)
            _midi_out = out
            log.info("Porta ALSA virtuale «%s» aperta per WebSocket MIDI", WS_ALSA_SOURCE_NAME)
            return True
        except Exception as exc:
            log.error("Impossibile aprire porta MIDI WS: %s", exc)
            return False


def _close_midi_out() -> None:
    global _midi_out
    with _midi_lock:
        if _midi_out is None:
            return
        try:
            _midi_out.close_port()
        except Exception:
            pass
        _midi_out = None


def _send_midi_bytes(payload: list[int]) -> None:
    if not payload:
        return
    data = [int(b) & 0xFF for b in payload]
    with _midi_lock:
        if _midi_out is None:
            return
        try:
            _midi_out.send_message(data)
            from activity_status import touch_midi_activity

            touch_midi_activity()
        except Exception as exc:
            log.warning("Invio MIDI WS → ALSA fallito: %s", exc)


def _handle_message(raw: str) -> None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return
    if data.get("id") != JZZ_OUTPUT_NAME:
        return
    midi = data.get("midi")
    if not isinstance(midi, dict):
        return
    payload = midi.get("midi")
    if isinstance(payload, list):
        _send_midi_bytes(payload)


async def _client_handler(websocket) -> None:
    _clients.add(websocket)
    try:
        await websocket.send(_info_payload())
        async for message in websocket:
            if isinstance(message, bytes):
                try:
                    message = message.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            _handle_message(message)
    except Exception as exc:
        log.debug("Client WS disconnesso: %s", exc)
    finally:
        _clients.discard(websocket)


async def _run_server(port: int) -> None:
    import websockets

    async with websockets.serve(
        _client_handler,
        "0.0.0.0",
        port,
        ping_interval=20,
        ping_timeout=20,
        max_size=2**20,
    ):
        log.info("WebSocket MIDI in ascolto su 0.0.0.0:%d (JZZ output «%s»)", port, JZZ_OUTPUT_NAME)
        await asyncio.Future()


def _run_loop(port: int) -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_server(port))
    finally:
        loop.close()


def ws_server_status() -> dict:
    port = _ws_port()
    return {
        "active": _midi_out is not None and not _stop.is_set(),
        "port": port,
        "output_name": JZZ_OUTPUT_NAME,
        "alsa_source": WS_ALSA_SOURCE_NAME,
        "clients": len(_clients),
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    port = _ws_port()
    if not _init_midi_out():
        return 1

    def _shutdown(*_args):
        log.info("Arresto server WebSocket MIDI…")
        _stop.set()
        _close_midi_out()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        _run_loop(port)
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

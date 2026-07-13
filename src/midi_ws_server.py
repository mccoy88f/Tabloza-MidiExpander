#!/usr/bin/env python3
"""Tabloza MidiExpander — WebSocket MIDI server (protocollo JZZ-midi-WS).

Espone la porta output «Tabloza Sing» verso browser Tabloza Sing; i byte MIDI
arrivano su una porta ALSA virtuale instradata dal orchestrator verso Tabloza Sing WS.
"""

from __future__ import annotations

import asyncio
import http
import json
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("tabloza.midi.ws")

# Nome vista dal client JZZ.WS (deve coincidere con Tabloza Sing frontend).
JZZ_OUTPUT_NAME = "Tabloza Sing"
# Porta ALSA virtuale (sorgente verso il gateway WS).
WS_ALSA_SOURCE_NAME = "Tabloza Sing"
DEFAULT_WS_PORT = 8765
WS_MIDI_CLIENTS_FILE = Path("/run/tabloza/ws_midi_clients.json")

_midi_out = None
_midi_lock = threading.Lock()
_clients: set[object] = set()
_stop = threading.Event()


def _persist_ws_clients() -> None:
    try:
        WS_MIDI_CLIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        WS_MIDI_CLIENTS_FILE.write_text(
            json.dumps({"clients": len(_clients), "ts": time.time()}),
        )
    except OSError:
        pass


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
    peer = getattr(websocket, "remote_address", None)
    log.info("Client WSS connesso da %s", peer)
    _clients.add(websocket)
    _persist_ws_clients()
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
        log.debug("Client WSS disconnesso: %s", exc)
    finally:
        _clients.discard(websocket)
        _persist_ws_clients()


_SETUP_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tabloza MidiExpander — Setup WSS</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.5; color: #e8fff9; background: #0f172a; max-width: 40rem; }}
    h1 {{ font-size: 1.25rem; }}
    p {{ color: #94a3b8; }}
    .ok {{ color: #5eead4; font-weight: 600; }}
    code {{ color: #cbd5e1; }}
    a {{ color: #5eead4; }}
    .buttons {{ display: flex; gap: 0.75rem; margin-top: 1.5rem; flex-wrap: wrap; }}
    .btn {{ display: inline-block; padding: 0.6rem 1.2rem; border-radius: 0.5rem; font-weight: 600; font-size: 1rem; font-family: inherit; text-decoration: none; cursor: pointer; }}
    .btn-primary {{ background: #5eead4; color: #0f172a; border: none; }}
    .btn-secondary {{ background: transparent; color: #5eead4; border: 1px solid #5eead4; }}
  </style>
</head>
<body>
  <h1>Certificato WSS accettato</h1>
  <p class="ok">Porta {port} pronta per Tabloza Sing (<code>wss://{host}:{port}</code>).</p>
  <p>Chiudi questa scheda e torna al Display su tabloza.live. Se il browser lo chiede, consenti anche <strong>Rete locale</strong> per tabloza.live.</p>
  <div class="buttons">
    <button type="button" class="btn btn-primary" onclick="closeTab()">Chiudi e torna a Tabloza</button>
    <a class="btn btn-secondary" href="http://{host}/">Impostazioni MidiExpander</a>
  </div>
  <script>
    function closeTab() {{
      window.close();
      setTimeout(function () {{ location.href = "https://tabloza.live"; }}, 300);
    }}
  </script>
</body>
</html>"""


def _setup_page_body() -> bytes:
    port = _ws_port()
    try:
        from tabloza_common import MDNS_NAME

        host = MDNS_NAME
    except Exception:
        host = "tabloza-me.local"
    return _SETUP_HTML.format(port=port, host=host).encode("utf-8")


def _is_websocket_upgrade(headers) -> bool:
    if headers is None:
        return False
    upgrade = (headers.get("Upgrade") or "").lower()
    return upgrade == "websocket"


def _make_process_request():
    """Compat websockets 12 (path, headers) e 13+ (connection, request → Response)."""
    import websockets

    ver = tuple(int(x) for x in websockets.__version__.split(".")[:2])

    if ver >= (13, 0):
        from websockets.datastructures import Headers
        from websockets.http11 import Response

        async def process_request(connection, request):
            path = (getattr(request, "path", None) or "/").split("?", 1)[0]
            if path not in ("/", "/setup"):
                return None
            if _is_websocket_upgrade(getattr(request, "headers", None)):
                return None
            body = _setup_page_body()
            headers = Headers()
            headers["Content-Type"] = "text/html; charset=utf-8"
            headers["Cache-Control"] = "no-store"
            return Response(200, "OK", headers, body)

        return process_request

    async def process_request(path, request_headers):
        path = (path or "/").split("?", 1)[0]
        if path not in ("/", "/setup"):
            return None
        if _is_websocket_upgrade(request_headers):
            return None
        body = _setup_page_body()
        return (
            http.HTTPStatus.OK,
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-store"),
            ],
            body,
        )

    return process_request


async def _run_server(port: int) -> None:
    import websockets

    from tls_utils import load_ssl_context

    ssl_context = load_ssl_context()
    process_request = _make_process_request()
    async with websockets.serve(
        _client_handler,
        "0.0.0.0",
        port,
        ssl=ssl_context,
        process_request=process_request,
        ping_interval=20,
        ping_timeout=20,
        max_size=2**20,
    ):
        log.info(
            "WebSocket MIDI (WSS) in ascolto su 0.0.0.0:%d (JZZ output «%s»)",
            port,
            JZZ_OUTPUT_NAME,
        )
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
        "tls": True,
        "scheme": "wss",
        "setup_path": "/setup",
        "output_name": JZZ_OUTPUT_NAME,
        "alsa_source": WS_ALSA_SOURCE_NAME,
        "clients": len(_clients),
    }


def _midi_init_loop() -> None:
    """Apre la porta ALSA virtuale in background (non blocca l'avvio WSS)."""
    while not _stop.is_set():
        if _init_midi_out():
            return
        time.sleep(2)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    port = _ws_port()
    try:
        from tls_utils import ensure_tls_certificate

        ensure_tls_certificate()
    except Exception as exc:
        log.error("Certificato TLS non disponibile: %s", exc)
        return 1

    threading.Thread(target=_midi_init_loop, daemon=True, name="tabloza-midi-ws-init").start()

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
    except Exception as exc:
        log.error("Server WSS terminato: %s", exc)
        return 1
    finally:
        _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

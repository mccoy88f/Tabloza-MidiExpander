"""Tabloza — gateway MIDI verso FluidSynth (buffer RTP + SysEx mode).

rtpmidid inoltra gli eventi ALSA in tempo reale senza usare i timestamp RTP.
Tabloza inserisce un gateway configurabile tra le sorgenti MIDI e FluidSynth:
- buffer anti-jitter RTP (opzionale, default 25 ms)
- cambio modalità banchi GM/GS/XG/MMA via SysEx (hardware-like)
"""

from __future__ import annotations

import heapq
import logging
import threading
import time
from dataclasses import dataclass, field

log = logging.getLogger("tabloza.midi.buffer")

VIRTUAL_PORT_NAME = "Tabloza Buffer"
BUFFER_CLIENT_MARKERS = ("tabloza buffer",)


def _is_buffer_input_port(port: dict) -> bool:
    name = port.get("name", "").lower().strip()
    client = port.get("client", "").lower()
    if name == VIRTUAL_PORT_NAME.lower() or VIRTUAL_PORT_NAME.lower() in name:
        return True
    if any(marker in client for marker in BUFFER_CLIENT_MARKERS):
        return True
    return VIRTUAL_PORT_NAME.lower() in client

try:
    import rtmidi
except ImportError:
    rtmidi = None

from rtmidi_compat import (
    configure_midi_in,
    is_usable_python_rtmidi,
    make_midi_in,
    make_midi_out,
    rtmidi_diagnostic,
)


@dataclass(order=True)
class _QueuedMsg:
    release_at: float
    seq: int
    message: tuple = field(compare=False)


class MidiGateway:
    def __init__(
        self,
        buffer_ms: int,
        *,
        sysex_auto: bool = True,
        port_name: str | None = None,
    ):
        self.port_name = port_name or VIRTUAL_PORT_NAME
        self.buffer_ms = max(0, buffer_ms)
        self.sysex_auto = sysex_auto
        self._stop = threading.Event()
        self._midi_in = None
        self._midi_out = None
        self._writer_thread: threading.Thread | None = None
        self._queue: list[_QueuedMsg] = []
        self._queue_lock = threading.Lock()
        self._seq = 0
        self._active = False
        self._input_port_address: str | None = None
        self._output_lock = threading.RLock()

    @property
    def active(self) -> bool:
        return self._active

    @property
    def input_port_address(self) -> str | None:
        return self._input_port_address

    def _wait_for_input_port_address(self, timeout: float = 2.0) -> str | None:
        from midi_utils import get_input_ports, get_output_ports

        target = self.port_name.lower()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for port in get_input_ports() + get_output_ports():
                name = port.get("name", "").strip()
                if name == self.port_name or name.lower() == target:
                    log.info(
                        "Gateway MIDI input ALSA %s (%s)",
                        port["address"],
                        name,
                    )
                    return port["address"]
            time.sleep(0.1)
        return None

    def start(self) -> bool:
        if not is_usable_python_rtmidi():
            log.warning("python-rtmidi non utilizzabile — %s", rtmidi_diagnostic())
            return False

        self.stop()
        try:
            self._midi_in = make_midi_in()
            configure_midi_in(self._midi_in)
            self._midi_in.set_callback(self._on_message)
            self._midi_in.open_virtual_port(self.port_name)
            self._input_port_address = self._wait_for_input_port_address()
            if not self._input_port_address:
                log.warning("Gateway MIDI: porta ALSA Tabloza Buffer non trovata")
                self.stop()
                return False

            self._midi_out = make_midi_out()
            if not self._connect_output_to_fluidsynth():
                log.warning("Gateway MIDI: FluidSynth non trovato")
                self.stop()
                return False

            self._stop.clear()
            if self.buffer_ms > 0:
                self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
                self._writer_thread.start()
            self._active = True
            if self.buffer_ms > 0 and self.sysex_auto:
                log.info("Gateway MIDI: buffer %d ms + SysEx auto", self.buffer_ms)
            elif self.buffer_ms > 0:
                log.info("Gateway MIDI RTP attivo: %d ms prima di FluidSynth", self.buffer_ms)
            elif self.sysex_auto:
                log.info("Gateway MIDI: SysEx auto (passthrough)")
            return True
        except Exception as exc:
            log.error("Gateway MIDI non avviato: %s (%s)", exc, rtmidi_diagnostic())
            self.stop()
            return False

    def stop(self):
        self._stop.set()
        if self._midi_in:
            try:
                self._midi_in.cancel_callback()
                self._midi_in.close_port()
            except Exception:
                pass
            self._midi_in = None
        if self._midi_out:
            try:
                self._midi_out.close_port()
            except Exception:
                pass
            self._midi_out = None
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2)
        self._writer_thread = None
        with self._queue_lock:
            self._queue.clear()
        self._input_port_address = None
        self._active = False
        self._stop.clear()

    def reconnect_output(self) -> bool:
        if not self._active:
            return False
        with self._output_lock:
            try:
                if self._midi_out:
                    self._midi_out.close_port()
            except Exception:
                pass
            if not is_usable_python_rtmidi():
                return False
            self._midi_out = make_midi_out()
            ok = self._connect_output_to_fluidsynth()
            if not ok:
                log.warning("Gateway MIDI: riconnessione FluidSynth fallita")
            return ok

    def _connect_output_to_fluidsynth(self) -> bool:
        from midi_utils import find_fluidsynth_input

        fs = find_fluidsynth_input()
        if not fs or not self._midi_out:
            return False

        target_addr = fs["address"]
        target_client = fs["client"].lower()
        for i in range(self._midi_out.get_port_count()):
            name = self._midi_out.get_port_name(i)
            label = name.lower()
            if target_addr in name or target_client in label:
                self._midi_out.open_port(i)
                log.info("Gateway MIDI → %s (%s)", target_addr, name)
                return True
        return False

    def _inspect_sysex(self, message: tuple) -> bool:
        if not self.sysex_auto:
            return False
        from midi_sysex_mode import maybe_apply_sysex_bank_mode
        return maybe_apply_sysex_bank_mode(message)

    def _midi_bytes(self, message) -> list[int]:
        """Flatten ALSA/rtmidi payloads (int, bytes, list, tuple) to 0-255 ints."""
        out: list[int] = []

        def walk(part) -> None:
            if isinstance(part, (list, tuple)):
                for item in part:
                    walk(item)
            elif isinstance(part, (bytes, bytearray)):
                out.extend(int(b) & 0xFF for b in part)
            else:
                out.append(int(part) & 0xFF)

        walk(message)
        return out

    def _split_midi_messages(self, data: list[int]) -> list[list[int]]:
        """Split a flat byte stream into individual MIDI messages for rtmidi."""
        if not data:
            return []
        data = [int(b) & 0xFF for b in data]
        while data and data[0] == 0:
            data = data[1:]
        if not data:
            return []

        messages: list[list[int]] = []
        i = 0
        running_status: int | None = None
        while i < len(data):
            b = data[i]
            if b >= 0x80:
                if b == 0xF0:
                    j = i + 1
                    while j < len(data) and data[j] != 0xF7:
                        j += 1
                    if j < len(data):
                        j += 1
                    messages.append(data[i:j])
                    i = j
                    running_status = None
                    continue
                if b in (0xF1, 0xF3):
                    msg_len = 2
                elif b == 0xF2:
                    msg_len = 3
                elif b >= 0xF4:
                    msg_len = 1
                else:
                    hi = b & 0xF0
                    msg_len = 2 if hi in (0xC0, 0xD0) else 3
                chunk = data[i : i + msg_len]
                if len(chunk) == msg_len:
                    messages.append(chunk)
                i += msg_len
                # PC/CP do not leave running status: SMF players often emit a
                # spurious 0x00 after PC that would become prog 0 on same channel.
                if b < 0xF0 and (b & 0xF0) in (0xC0, 0xD0):
                    running_status = None
                elif b < 0xF0 and b >= 0xF4:
                    running_status = None
                elif 0xF0 <= b <= 0xF7:
                    running_status = None
                elif b < 0xF0:
                    running_status = b
            elif running_status is not None:
                hi = running_status & 0xF0
                if hi in (0xC0, 0xD0):
                    messages.append([running_status, b])
                    running_status = None
                    i += 1
                elif i + 1 < len(data):
                    messages.append([running_status, b, data[i + 1]])
                    i += 2
                else:
                    break
            else:
                i += 1
        return messages

    def _is_forwardable(self, part: list[int]) -> bool:
        if not part:
            return False
        status = part[0]
        # Meta events from SMF players (FF xx …) are not wire MIDI — skip.
        if status == 0xFF and len(part) > 1:
            return False
        if status == 0xF0:
            return True
        if 0x80 <= status <= 0xEF:
            hi = status & 0xF0
            need = 2 if hi in (0xC0, 0xD0) else 3
            return len(part) == need
        if 0xF8 <= status <= 0xFF:
            return len(part) == 1
        return False

    def _forward_message(self, message: tuple):
        from activity_status import touch_midi_activity

        parts = [
            p for p in self._split_midi_messages(self._midi_bytes(message))
            if self._is_forwardable(p)
        ]
        if not parts:
            return
        with self._output_lock:
            if not self._midi_out:
                return
            for payload in parts:
                if payload and payload[0] == 0xF0:
                    from midi_sysex_mode import repair_gs_sysex_checksum
                    payload = repair_gs_sysex_checksum(payload)
                try:
                    self._midi_out.send_message(payload)
                    touch_midi_activity()
                except Exception as exc:
                    log.warning("Invio gateway MIDI fallito: %s", exc)
                    if self.reconnect_output():
                        try:
                            self._midi_out.send_message(payload)
                            touch_midi_activity()
                        except Exception:
                            pass
                    break

    def _on_message(self, message, _data=None):
        from activity_status import touch_midi_activity

        msg = tuple(message)
        if not msg:
            return
        touch_midi_activity()
        if self._inspect_sysex(msg):
            return
        if self.buffer_ms <= 0:
            self._forward_message(msg)
            return
        release_at = time.monotonic() + (self.buffer_ms / 1000.0)
        self._seq += 1
        item = _QueuedMsg(release_at, self._seq, msg)
        with self._queue_lock:
            heapq.heappush(self._queue, item)

    def _writer_loop(self):
        while not self._stop.is_set():
            now = time.monotonic()
            batch: list[tuple] = []
            with self._queue_lock:
                while self._queue and self._queue[0].release_at <= now:
                    batch.append(heapq.heappop(self._queue).message)

            if not batch:
                time.sleep(0.001)
                continue

            for msg in batch:
                self._forward_message(msg)


_gateway: MidiGateway | None = None
_gateway_lock = threading.Lock()


def ensure_midi_gateway(buffer_ms: int, *, sysex_auto: bool = True) -> bool:
    """Start or update the MIDI gateway; return True if active."""
    global _gateway
    need = buffer_ms > 0 or sysex_auto
    with _gateway_lock:
        if not need:
            if _gateway:
                _gateway.stop()
                _gateway = None
            return False
        if (
            _gateway
            and _gateway.active
            and _gateway.buffer_ms == max(0, buffer_ms)
            and _gateway.sysex_auto == sysex_auto
        ):
            return True
        if _gateway:
            _gateway.stop()
        _gateway = MidiGateway(max(0, buffer_ms), sysex_auto=sysex_auto)
        if _gateway.start():
            return True
        log.error("Gateway MIDI: avvio fallito — %s", rtmidi_diagnostic())
        _gateway = None
        return False


def ensure_jitter_buffer(buffer_ms: int, *, sysex_auto: bool = True) -> bool:
    """Backward-compatible alias."""
    return ensure_midi_gateway(buffer_ms, sysex_auto=sysex_auto)


def stop_jitter_buffer():
    global _gateway
    with _gateway_lock:
        if _gateway:
            _gateway.stop()
            _gateway = None


def reconnect_jitter_buffer_output() -> bool:
    with _gateway_lock:
        if _gateway and _gateway.active:
            return _gateway.reconnect_output()
        return False


def jitter_buffer_active() -> bool:
    with _gateway_lock:
        return bool(_gateway and _gateway.active)


def get_buffer_input_port() -> dict | None:
    """Return ALSA input port dict for routing sources into the gateway."""
    with _gateway_lock:
        cached = _gateway.input_port_address if _gateway and _gateway.active else None
        local_active = bool(_gateway and _gateway.active)
    if cached:
        return {
            "client": VIRTUAL_PORT_NAME,
            "name": VIRTUAL_PORT_NAME,
            "address": cached,
        }
    from midi_utils import get_buffer_ports, orchestrator_running

    if local_active or orchestrator_running():
        for port in get_buffer_ports():
            if _is_buffer_input_port(port):
                return port
    return None


def jitter_buffer_status() -> dict:
    from midi_config import merge_midi_config
    from midi_utils import orchestrator_running
    from tabloza_common import load_config

    with _gateway_lock:
        local_active = bool(_gateway and _gateway.active)
        ms = _gateway.buffer_ms if _gateway else 0
        sysex_auto = _gateway.sysex_auto if _gateway else False
    port = get_buffer_input_port()
    alsa_active = port is not None and orchestrator_running()
    active = local_active or alsa_active
    if not local_active and alsa_active:
        cfg = load_config()
        midi = merge_midi_config(cfg.get("midi") if isinstance(cfg.get("midi"), dict) else None)
        ms = midi["jitter_buffer_ms"] if midi["jitter_buffer_enabled"] else 0
        sysex_auto = midi["sysex_bank_auto"]
    from midi_sysex_mode import get_runtime_bank_select

    return {
        "active": active,
        "buffer_ms": ms if active else 0,
        "sysex_auto": sysex_auto,
        "runtime_bank_select": get_runtime_bank_select(),
        "input_port": port,
        "rtmidi_available": is_usable_python_rtmidi(),
    }

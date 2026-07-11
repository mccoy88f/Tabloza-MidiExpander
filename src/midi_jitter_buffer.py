"""Tabloza — playout buffer MIDI (anti-jitter rete RTP).

rtpmidid inoltra gli eventi ALSA in tempo reale senza usare i timestamp RTP.
Tabloza inserisce un buffer configurabile (default 25 ms) tra le sorgenti MIDI
e FluidSynth, in linea con le linee guida RTP-MIDI per reti con jitter.
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

try:
    import rtmidi
except ImportError:
    rtmidi = None


@dataclass(order=True)
class _QueuedMsg:
    release_at: float
    seq: int
    message: tuple = field(compare=False)


class MidiJitterBuffer:
    def __init__(self, buffer_ms: int):
        self.buffer_ms = buffer_ms
        self._stop = threading.Event()
        self._midi_in = None
        self._midi_out = None
        self._writer_thread: threading.Thread | None = None
        self._queue: list[_QueuedMsg] = []
        self._queue_lock = threading.Lock()
        self._seq = 0
        self._active = False
        self._output_lock = threading.RLock()

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> bool:
        if self.buffer_ms <= 0:
            return False
        if rtmidi is None:
            log.warning("python-rtmidi non disponibile — buffer MIDI disattivato")
            return False

        self.stop()
        try:
            self._midi_in = rtmidi.MidiIn(rtmidi.API_UNIX_ALSA)
            self._midi_in.ignore_types(sysex=False, timing=False, active_sensing=False)
            self._midi_in.set_callback(self._on_message)
            self._midi_in.open_virtual_port(VIRTUAL_PORT_NAME)

            self._midi_out = rtmidi.MidiOut(rtmidi.API_UNIX_ALSA)
            if not self._connect_output_to_fluidsynth():
                log.warning("Buffer MIDI: FluidSynth non trovato")
                self.stop()
                return False

            self._stop.clear()
            self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
            self._writer_thread.start()
            self._active = True
            log.info("Buffer MIDI RTP attivo: %d ms prima di FluidSynth", self.buffer_ms)
            return True
        except Exception as exc:
            log.error("Buffer MIDI non avviato: %s", exc)
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
            if rtmidi is None:
                return False
            self._midi_out = rtmidi.MidiOut(rtmidi.API_UNIX_ALSA)
            ok = self._connect_output_to_fluidsynth()
            if not ok:
                log.warning("Buffer MIDI: riconnessione FluidSynth fallita")
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
                log.info("Buffer MIDI → %s (%s)", target_addr, name)
                return True
        return False

    def _on_message(self, message, _data=None):
        release_at = time.monotonic() + (self.buffer_ms / 1000.0)
        self._seq += 1
        item = _QueuedMsg(release_at, self._seq, tuple(message))
        with self._queue_lock:
            heapq.heappush(self._queue, item)

    def _writer_loop(self):
        from activity_status import touch_midi_activity

        while not self._stop.is_set():
            now = time.monotonic()
            batch: list[tuple] = []
            with self._queue_lock:
                while self._queue and self._queue[0].release_at <= now:
                    batch.append(heapq.heappop(self._queue).message)

            if not batch:
                time.sleep(0.001)
                continue

            with self._output_lock:
                if not self._midi_out:
                    continue
                for msg in batch:
                    try:
                        self._midi_out.send_message(list(msg))
                        touch_midi_activity()
                    except Exception as exc:
                        log.warning("Invio buffer MIDI fallito: %s", exc)
                        if not self.reconnect_output():
                            break
                        try:
                            self._midi_out.send_message(list(msg))
                            touch_midi_activity()
                        except Exception:
                            break


_buffer: MidiJitterBuffer | None = None
_buffer_lock = threading.Lock()


def ensure_jitter_buffer(buffer_ms: int) -> bool:
    """Start or update the MIDI jitter buffer; return True if active."""
    global _buffer
    with _buffer_lock:
        if buffer_ms <= 0:
            if _buffer:
                _buffer.stop()
                _buffer = None
            return False
        if _buffer and _buffer.active and _buffer.buffer_ms == buffer_ms:
            return True
        if _buffer:
            _buffer.stop()
        _buffer = MidiJitterBuffer(buffer_ms)
        if _buffer.start():
            return True
        _buffer = None
        return False


def stop_jitter_buffer():
    global _buffer
    with _buffer_lock:
        if _buffer:
            _buffer.stop()
            _buffer = None


def reconnect_jitter_buffer_output() -> bool:
    with _buffer_lock:
        if _buffer and _buffer.active:
            return _buffer.reconnect_output()
        return False


def jitter_buffer_active() -> bool:
    with _buffer_lock:
        return bool(_buffer and _buffer.active)


def get_buffer_input_port() -> dict | None:
    """Return ALSA input port dict for routing sources into the buffer."""
    if not jitter_buffer_active():
        return None
    from midi_utils import get_input_ports

    for port in get_input_ports():
        if any(marker in port["client"].lower() for marker in BUFFER_CLIENT_MARKERS):
            return port
        if VIRTUAL_PORT_NAME.lower() in f"{port['client']} {port['name']}".lower():
            return port
    return None


def jitter_buffer_status() -> dict:
    with _buffer_lock:
        active = bool(_buffer and _buffer.active)
        ms = _buffer.buffer_ms if _buffer else 0
    port = get_buffer_input_port() if active else None
    return {
        "active": active,
        "buffer_ms": ms if active else 0,
        "input_port": port,
        "rtmidi_available": rtmidi is not None,
    }

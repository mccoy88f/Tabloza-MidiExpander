"""Tabloza — utilità audio ALSA."""

import math
import struct
import subprocess


def play_stereo_tone(
    device: str,
    frequency: float = 440.0,
    duration_sec: float = 2.5,
    sample_rate: int = 44100,
    volume: float = 0.4,
) -> None:
    """Play the same sine tone on left and right (stereo jack test)."""
    n_samples = int(sample_rate * duration_sec)
    amp = int(32767 * volume)
    buf = bytearray()
    for i in range(n_samples):
        sample = int(amp * math.sin(2 * math.pi * frequency * i / sample_rate))
        buf += struct.pack("<hh", sample, sample)
    subprocess.run(
        ["aplay", "-D", device, "-f", "S16_LE", "-r", str(sample_rate), "-c", "2", "-q"],
        input=bytes(buf),
        timeout=duration_sec + 5,
        check=True,
    )

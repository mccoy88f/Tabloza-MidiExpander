"""Tabloza — utilità audio ALSA."""

import logging
import math
import re
import struct
import subprocess

log = logging.getLogger("tabloza.audio")

PREFERRED_MIXER_CONTROLS = ("PCM", "Headphone", "HP", "Master", "Digital", "Playback")
PLAYBACK_DEVICE_RE = re.compile(
    r"^card (\d+): .+ \[([^\]]+)\], device (\d+):",
)
AUDIO_DEVICE_ID_RE = re.compile(r"^(?:plug)?hw:(\d+),(\d+)$")


def card_from_audio_device(device: str) -> int:
    match = AUDIO_DEVICE_ID_RE.match(device.strip())
    return int(match.group(1)) if match else 0


def alsa_device_for_card(card: int, device: int = 0) -> str:
    """USB cards often need hw: at 48 kHz; built-in jack tolerates plughw:."""
    if card == 0:
        return f"plughw:{card},{device}"
    return f"hw:{card},{device}"


def sample_rate_for_device(device: str, default: int = 44100) -> int:
    card = card_from_audio_device(device)
    return 48000 if card > 0 else default


def list_playback_devices() -> list[dict]:
    """List ALSA playback devices via `aplay -l`."""
    try:
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True, text=True, timeout=5, check=True,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return []

    devices = []
    for line in result.stdout.splitlines():
        match = PLAYBACK_DEVICE_RE.match(line.strip())
        if not match:
            continue
        card_i, name, dev = match.groups()
        card_i, dev_i = int(card_i), int(dev)
        devices.append({
            "card": card_i,
            "device": dev_i,
            "id": alsa_device_for_card(card_i, dev_i),
            "name": name.strip(),
            "label": f"{name.strip()} (card {card_i})",
            "sample_rate": sample_rate_for_device(alsa_device_for_card(card_i, dev_i)),
        })
    return devices


def device_label(device_id: str, devices: list[dict] | None = None) -> str:
    for dev in devices or list_playback_devices():
        if dev["id"] == device_id:
            return dev["label"]
    return device_id


def audio_device_available(device: str) -> bool:
    match = AUDIO_DEVICE_ID_RE.match(device.strip())
    if not match:
        return False
    card, dev = match.groups()
    for d in list_playback_devices():
        if d["card"] == int(card) and d["device"] == int(dev):
            return True
    return False


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


def _mixer_controls(card: int) -> list[str]:
    try:
        result = subprocess.run(
            ["amixer", "-c", str(card), "scontrols"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return re.findall(r"Simple mixer control '([^']+)'", result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return []


def resolve_mixer_control(card: int = 0, control: str | None = None) -> str | None:
    available = _mixer_controls(card)
    if control and control in available:
        return control
    for name in PREFERRED_MIXER_CONTROLS:
        if name in available:
            return name
    return available[0] if available else None


def volume_to_alsa_percent(volume: int) -> int:
    vol = max(0, min(127, int(volume)))
    return int(round(vol / 127.0 * 100))


def set_alsa_output_volume(
    volume: int,
    card: int = 0,
    control: str | None = None,
) -> tuple[bool, str]:
    """Set ALSA mixer level for the analog output (headphone jack / USB DAC)."""
    percent = volume_to_alsa_percent(volume)
    target = resolve_mixer_control(card, control)
    if not target:
        return False, f"Nessun controllo mixer ALSA sulla card {card}"

    def _run_amixer(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["amixer", "-c", str(card), *args],
            capture_output=True, text=True, timeout=5, check=False,
        )

    try:
        if percent == 0:
            result = _run_amixer(["sset", target, "off"])
        else:
            result = _run_amixer(["sset", target, f"{percent}%"])
            if result.returncode != 0:
                result = _run_amixer(["sset", target, "on"])
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "amixer fallito").strip()
            return False, err
        if percent == 0:
            detail = f"{target}=off (card {card})"
        elif "pvolume" not in (result.stdout or "").lower() and "Playback [on]" in (result.stdout or ""):
            detail = f"{target}=on (card {card}, switch)"
        else:
            detail = f"{target}={percent}% (card {card})"
        log.info("Volume ALSA: %s", detail)
        return True, detail
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return False, str(exc)


def apply_output_volume(volume: int, config: dict) -> tuple[bool, str]:
    """Apply master volume on the ALSA output path (jack / DAC)."""
    fs_cfg = config.get("fluidsynth", {})
    return set_alsa_output_volume(
        volume,
        card=int(fs_cfg.get("alsa_card", 0)),
        control=fs_cfg.get("alsa_mixer_control"),
    )

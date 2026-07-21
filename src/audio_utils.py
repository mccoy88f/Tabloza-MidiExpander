"""Tabloza — utilità audio ALSA (pyalsaaudio)."""

import logging
import math
import re
import struct
import subprocess

import alsaaudio

log = logging.getLogger("tabloza.audio")

PREFERRED_MIXER_CONTROLS = ("PCM", "Headphone", "HP", "Master", "Digital", "Playback")
AUDIO_DEVICE_ID_RE = re.compile(r"^(?:plug)?hw:(\d+),(\d+)$")
APLAY_PLAYBACK_RE = re.compile(
    r"^card (\d+): (.+?), device (\d+): (.+)$",
)
FALLBACK_AUDIO_DEVICE = "plughw:0,0"


def card_from_audio_device(device: str) -> int:
    match = AUDIO_DEVICE_ID_RE.match(device.strip())
    return int(match.group(1)) if match else 0


def _card_names() -> list[str]:
    try:
        return list(alsaaudio.cards())
    except alsaaudio.ALSAAudioError:
        return []


def _needs_plughw(card: int, card_name: str = "") -> bool:
    """Jack and HDMI (IEC958) need plughw; USB DACs often work with hw:."""
    if card == 0:
        return True
    name = card_name.lower()
    return "hdmi" in name or "vc4" in name


def alsa_device_for_card(card: int, device: int = 0, card_name: str | None = None) -> str:
    if card_name is None:
        names = _card_names()
        card_name = names[card] if card < len(names) else ""
    prefix = "plughw" if _needs_plughw(card, card_name) else "hw"
    return f"{prefix}:{card},{device}"


def resolve_audio_device(device: str) -> str:
    """Map stored device id to the ALSA id FluidSynth can open (e.g. hw:2,0 → plughw:2,0 for HDMI)."""
    match = AUDIO_DEVICE_ID_RE.match(device.strip())
    if not match:
        return device.strip()
    card, dev = int(match.group(1)), int(match.group(2))
    return alsa_device_for_card(card, dev)


def sample_rate_for_device(device: str, default: int = 44100) -> int:
    card = card_from_audio_device(device)
    return 48000 if card > 0 else default


def normalize_volume(volume: int) -> int:
    """0–100 percent; migrate legacy 0–127 MIDI-style values."""
    vol = int(volume)
    if vol > 100:
        vol = round(vol / 127 * 100)
    return max(0, min(100, vol))


def volume_to_alsa_percent(volume: int) -> int:
    return normalize_volume(volume)


def _short_aplay_name(text: str) -> str:
    text = text.strip()
    if "[" in text:
        return text.split("[", 1)[0].strip()
    return text


def parse_aplay_playback(output: str) -> list[tuple[int, int, str, str]]:
    """Parse `aplay -l` playback lines → (card, device, card_name, pcm_name)."""
    entries: list[tuple[int, int, str, str]] = []
    for line in output.splitlines():
        match = APLAY_PLAYBACK_RE.match(line.strip())
        if not match:
            continue
        card_i = int(match.group(1))
        dev_i = int(match.group(3))
        card_name = _short_aplay_name(match.group(2))
        pcm_name = _short_aplay_name(match.group(4))
        entries.append((card_i, dev_i, card_name, pcm_name))
    return entries


def _playback_entries_from_aplay() -> list[tuple[int, int, str, str]] | None:
    try:
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    entries = parse_aplay_playback(result.stdout)
    return entries or None


def _build_playback_device(
    card_i: int,
    dev_i: int,
    card_name: str,
    pcm_name: str = "",
) -> dict:
    device_id = alsa_device_for_card(card_i, dev_i, card_name)
    sample_rate = sample_rate_for_device(device_id)
    label = card_name.strip()
    if pcm_name and pcm_name.lower() != label.lower():
        label = f"{label} — {pcm_name.strip()}"
    label = f"{label} (card {card_i})"
    return {
        "card": card_i,
        "device": dev_i,
        "id": device_id,
        "name": card_name.strip(),
        "pcm_name": pcm_name.strip(),
        "label": label,
        "sample_rate": sample_rate,
    }


def list_playback_devices() -> list[dict]:
    """List ALSA playback devices (jack, USB, HDMI…) via aplay or pyalsaaudio."""
    devices: list[dict] = []
    seen: set[str] = set()

    aplay_entries = _playback_entries_from_aplay()
    if aplay_entries:
        for card_i, dev_i, card_name, pcm_name in aplay_entries:
            dev = _build_playback_device(card_i, dev_i, card_name, pcm_name)
            dev["kind"] = "alsa"
            if dev["id"] not in seen:
                seen.add(dev["id"])
                devices.append(dev)
        if devices:
            return devices

    try:
        cards = alsaaudio.cards()
    except alsaaudio.ALSAAudioError:
        return []

    for card_i, name in enumerate(cards):
        dev = _build_playback_device(card_i, 0, name)
        dev["kind"] = "alsa"
        if dev["id"] not in seen:
            seen.add(dev["id"])
            devices.append(dev)
    return devices


def list_all_playback_devices() -> list[dict]:
    """ALSA devices plus optional Bluetooth sinks (Pulse/PipeWire)."""
    devices = list_playback_devices()
    try:
        from bluetooth_audio import list_bluetooth_sinks
        for bt in list_bluetooth_sinks():
            devices.append(bt)
    except Exception as exc:
        log.warning("Elenco Bluetooth non disponibile: %s", exc)
    return devices


def current_audio_device_id(fs_cfg: dict | None) -> str:
    """Canonical device id for UI/API (pulse:… for Bluetooth)."""
    fs = fs_cfg or {}
    driver = (fs.get("audio_driver") or "alsa").strip().lower()
    device = (fs.get("audio_device") or "plughw:0,0").strip()
    if driver == "pulse":
        from bluetooth_audio import is_pulse_device_id, pulse_device_id
        return device if is_pulse_device_id(device) else pulse_device_id(device)
    return resolve_audio_device(device)


def device_label(device_id: str, devices: list[dict] | None = None) -> str:
    for dev in devices or list_playback_devices():
        if dev["id"] == device_id:
            return dev["label"]
    return device_id


def probe_playback_device(device: str, sample_rate: int | None = None) -> tuple[bool, str | None]:
    """True if ALSA can open the playback PCM (HDMI without a sink often fails here)."""
    resolved = resolve_audio_device(device)
    rate = sample_rate if sample_rate is not None else sample_rate_for_device(resolved)
    try:
        pcm = _open_playback_pcm(resolved, rate)
        del pcm
        return True, None
    except alsaaudio.ALSAAudioError as exc:
        return False, str(exc)


def audio_device_available(device: str) -> bool:
    ok, _ = probe_playback_device(device)
    return ok


def apply_audio_fallback_if_needed(config: dict) -> tuple[dict, bool, str]:
    """Se l'uscita scelta non si apre (es. HDMI senza monitor), passa al jack."""
    from tabloza_common import save_config

    fs = dict(config.get("fluidsynth") or {})
    driver = (fs.get("audio_driver") or "alsa").strip().lower()
    if driver != "alsa":
        return config, False, ""

    device = str(fs.get("audio_device") or FALLBACK_AUDIO_DEVICE)
    if audio_device_available(device):
        return config, False, ""

    if device == FALLBACK_AUDIO_DEVICE or not audio_device_available(FALLBACK_AUDIO_DEVICE):
        return config, False, (
            f"Uscita audio non disponibile: {device}"
        )

    fs["audio_device"] = FALLBACK_AUDIO_DEVICE
    fs["alsa_card"] = card_from_audio_device(FALLBACK_AUDIO_DEVICE)
    config = {**config, "fluidsynth": fs}
    try:
        save_config({"fluidsynth": fs})
    except OSError:
        pass
    msg = (
        f"Uscita {device} non disponibile — fallback a {FALLBACK_AUDIO_DEVICE}"
    )
    return config, True, msg


def _open_playback_pcm(device: str, sample_rate: int, channels: int = 2) -> alsaaudio.PCM:
    """Open PCM, retrying plughw when hw fails (some cards)."""
    candidates = [device]
    if device.startswith("hw:") and not device.startswith("plughw:"):
        candidates.append("plug" + device)
    last_err: Exception | None = None
    for dev in candidates:
        try:
            pcm = alsaaudio.PCM(
                alsaaudio.PCM_PLAYBACK,
                alsaaudio.PCM_NORMAL,
                device=dev,
            )
            pcm.setchannels(channels)
            pcm.setrate(sample_rate)
            pcm.setformat(alsaaudio.PCM_FORMAT_S16_LE)
            pcm.setperiodsize(1024)
            return pcm
        except alsaaudio.ALSAAudioError as exc:
            last_err = exc
    raise last_err or alsaaudio.ALSAAudioError(f"Impossibile aprire {device}")


def play_stereo_tone(
    device: str,
    frequency: float = 440.0,
    duration_sec: float = 2.5,
    sample_rate: int = 44100,
    volume: float = 0.4,
) -> None:
    """Play the same sine tone on left and right on the given ALSA device."""
    pcm = _open_playback_pcm(device, sample_rate)
    period = 1024
    pcm.setperiodsize(period)
    amp = int(32767 * volume)
    total_samples = int(sample_rate * duration_sec)
    written = 0
    phase = 0.0
    phase_inc = 2 * math.pi * frequency / sample_rate

    while written < total_samples:
        chunk = min(period, total_samples - written)
        buf = bytearray()
        for _ in range(chunk):
            sample = int(amp * math.sin(phase))
            phase += phase_inc
            buf += struct.pack("<hh", sample, sample)
        pcm.write(bytes(buf))
        written += chunk


def _mixer_controls(card: int) -> list[str]:
    try:
        return alsaaudio.mixers(cardindex=card)
    except alsaaudio.ALSAAudioError:
        return []


def resolve_mixer_control(card: int = 0, control: str | None = None) -> str | None:
    available = _mixer_controls(card)
    if control and control in available:
        return control
    for name in PREFERRED_MIXER_CONTROLS:
        if name in available:
            return name
    return available[0] if available else None


def _mixer_has_volume(mix: alsaaudio.Mixer) -> bool:
    try:
        levels = mix.getvolume()
        return bool(levels)
    except alsaaudio.ALSAAudioError:
        return False


def _mixer_has_switch(mix: alsaaudio.Mixer) -> bool:
    try:
        mix.getswitch()
        return True
    except alsaaudio.ALSAAudioError:
        return False


def set_alsa_output_volume(
    volume: int,
    card: int = 0,
    control: str | None = None,
) -> tuple[bool, str]:
    """Set ALSA mixer level for the active output (jack / USB DAC)."""
    percent = volume_to_alsa_percent(volume)
    target = resolve_mixer_control(card, control)
    if not target:
        return False, f"Nessun controllo mixer ALSA sulla card {card}"

    try:
        mix = alsaaudio.Mixer(target, cardindex=card)
    except alsaaudio.ALSAAudioError as exc:
        return False, str(exc)

    try:
        if _mixer_has_volume(mix):
            if percent == 0:
                mix.setvolume(0)
            else:
                mix.setvolume(percent)
            detail = f"{target}={percent}% (card {card})"
            log.info("Volume ALSA: %s", detail)
            return True, detail

        if _mixer_has_switch(mix):
            mix.setswitch(1 if percent > 0 else 0)
            state = "on" if percent > 0 else "off"
            detail = f"{target}={state} (card {card}, switch)"
            log.info("Volume ALSA: %s", detail)
            return True, detail

        return False, f"Controllo {target} non gestibile sulla card {card}"
    except alsaaudio.ALSAAudioError as exc:
        return False, str(exc)


def apply_output_volume(volume: int, config: dict) -> tuple[bool, str]:
    """Apply master volume on the active output path (ALSA or Bluetooth/Pulse)."""
    fs_cfg = config.get("fluidsynth", {})
    driver = (fs_cfg.get("audio_driver") or "alsa").strip().lower()
    if driver == "pulse":
        from bluetooth_audio import pulse_sink_from_device_id, set_pulse_sink_volume
        sink = pulse_sink_from_device_id(fs_cfg.get("audio_device", ""))
        return set_pulse_sink_volume(sink, volume)
    # Card dal device attivo (non alsa_card stale da un'uscita precedente).
    device = str(fs_cfg.get("audio_device") or FALLBACK_AUDIO_DEVICE)
    card = card_from_audio_device(device)
    return set_alsa_output_volume(
        volume,
        card=card,
        control=fs_cfg.get("alsa_mixer_control"),
    )

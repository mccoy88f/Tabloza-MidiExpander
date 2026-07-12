"""Tabloza — genera e applica /etc/rtpmidid/default.ini da config.json."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RTPMIDID_INI_PATH = Path("/etc/rtpmidid/default.ini")


def render_rtpmidid_ini(*, use_rtp_midi_timestamps: bool = True) -> str:
    ts = "true" if use_rtp_midi_timestamps else "false"
    return f"""# Tabloza MidiExpander — rtpmidid-ts config (generato da Tabloza)
# Mac/Windows: una sola sessione RTP-MIDI "tabloza-me" (porta 5004).
# Il routing verso FluidSynth è interno (aconnect), non va annunciato in rete.

[general]
alsa_name=rtpmidid
control=/var/run/rtpmidid/control.sock
# Fork Tabloza: scheduling ALSA dai timestamp RTP (RFC 6295).
use_rtp_midi_timestamps={ts}
# Jitter WiFi gestito da Tabloza Buffer downstream — niente buffer extra qui.
playout_buffer_ms=0

[rtpmidi_announce]
name=tabloza-me
port=5004

# NON usare [alsa_announce]: esporrebbe FluidSynth come secondo endpoint di rete.
"""


def use_rtp_midi_timestamps_from_config(config: dict) -> bool:
    from midi_config import is_rtp_midi_timestamps_enabled

    return is_rtp_midi_timestamps_enabled(config)


def write_rtpmidid_ini(config: dict, dest: Path | None = None) -> Path:
    dest = dest or RTPMIDID_INI_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = render_rtpmidid_ini(
        use_rtp_midi_timestamps=use_rtp_midi_timestamps_from_config(config),
    )
    dest.write_text(content, encoding="utf-8")
    dest.chmod(0o644)
    return dest


def restart_rtpmidid() -> bool:
    try:
        subprocess.run(
            ["systemctl", "restart", "rtpmidid"],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def apply_rtpmidid_config(config: dict, *, restart: bool = True) -> bool:
    write_rtpmidid_ini(config)
    Path("/var/run/rtpmidid").mkdir(parents=True, exist_ok=True)
    if not restart:
        return True
    return restart_rtpmidid()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] != "apply":
        print("Usage: rtpmidid_config.py apply", file=sys.stderr)
        return 2

    from tabloza_common import load_config

    config = load_config()
    if not apply_rtpmidid_config(config):
        print("rtpmidid: apply config ok, restart failed", file=sys.stderr)
        return 1
    enabled = use_rtp_midi_timestamps_from_config(config)
    print(f"rtpmidid config applicata: use_rtp_midi_timestamps={enabled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

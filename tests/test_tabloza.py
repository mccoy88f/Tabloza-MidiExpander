#!/usr/bin/env python3
"""Unit tests for Tabloza core helpers."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from audio_utils import (  # noqa: E402
    card_from_audio_device,
    list_playback_devices,
    volume_to_alsa_percent,
)
from soundfont_config import startup_soundfont_name  # noqa: E402


APLAY_SAMPLE = """\
**** List of PLAYBACK Hardware Devices ****
card 0: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
  Subdevices: 4/4
card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio Device]
  Subdevices: 1/1
"""


class TestAudioUtils(unittest.TestCase):
    def test_card_from_audio_device(self):
        self.assertEqual(card_from_audio_device("plughw:1,0"), 1)
        self.assertEqual(card_from_audio_device("hw:0,0"), 0)
        self.assertEqual(card_from_audio_device("invalid"), 0)

    def test_volume_to_alsa_percent(self):
        self.assertEqual(volume_to_alsa_percent(0), 0)
        self.assertEqual(volume_to_alsa_percent(127), 100)
        self.assertEqual(volume_to_alsa_percent(64), 50)

    @patch("audio_utils.subprocess.run")
    def test_list_playback_devices(self, mock_run):
        mock_run.return_value.stdout = APLAY_SAMPLE
        mock_run.return_value.returncode = 0
        devices = list_playback_devices()
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0]["id"], "plughw:0,0")
        self.assertEqual(devices[1]["id"], "plughw:1,0")
        self.assertIn("USB Audio Device", devices[1]["name"])


class TestStartupSoundfont(unittest.TestCase):
    def test_prefers_default_over_active(self):
        root = Path("/tmp/tabloza-test-sf2")
        root.mkdir(exist_ok=True)
        (root / "default.sf2").write_bytes(b"x")
        (root / "active.sf2").write_bytes(b"x")
        config = {
            "default_soundfont": "default.sf2",
            "active_soundfont": "active.sf2",
        }
        self.assertEqual(startup_soundfont_name(config, root), "default.sf2")

    def test_falls_back_to_active(self):
        root = Path("/tmp/tabloza-test-sf2")
        root.mkdir(exist_ok=True)
        (root / "active.sf2").write_bytes(b"x")
        config = {"default_soundfont": "", "active_soundfont": "active.sf2"}
        self.assertEqual(startup_soundfont_name(config, root), "active.sf2")

    def test_missing_files_return_empty(self):
        root = Path("/tmp/tabloza-test-sf2-missing")
        config = {"default_soundfont": "nope.sf2", "active_soundfont": "also.sf2"}
        self.assertEqual(startup_soundfont_name(config, root), "")


if __name__ == "__main__":
    unittest.main()

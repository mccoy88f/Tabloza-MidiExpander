#!/usr/bin/env python3
"""Unit tests for Tabloza core helpers."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# pyalsaaudio is Linux-only; stub for local dev/test on macOS.
if "alsaaudio" not in sys.modules:
    try:
        import alsaaudio  # noqa: F401
    except ImportError:
        sys.modules["alsaaudio"] = MagicMock()

from audio_utils import (  # noqa: E402
    card_from_audio_device,
    list_playback_devices,
    normalize_volume,
    volume_to_alsa_percent,
)
from event_log import clear_events, log_event, read_events  # noqa: E402
from soundfont_config import startup_soundfont_name  # noqa: E402
from wifi_utils import connect_wifi_network, parse_nmcli_terse_fields  # noqa: E402


class TestSystemStats(unittest.TestCase):
    @patch("system_stats._read_meminfo_kb")
    @patch("system_stats._process_rss_mb")
    def test_get_memory_stats(self, mock_rss, mock_mem):
        mock_mem.return_value = {
            "MemTotal": 4 * 1024 * 1024,
            "MemAvailable": 2 * 1024 * 1024,
            "SwapTotal": 1024 * 1024,
            "SwapFree": 512 * 1024,
        }
        mock_rss.side_effect = lambda *a, **k: 120 if a[0] == "fluidsynth" else 40
        from system_stats import get_memory_stats

        stats = get_memory_stats()
        self.assertEqual(stats["total_mb"], 4096)
        self.assertEqual(stats["available_mb"], 2048)
        self.assertEqual(stats["used_mb"], 2048)
        self.assertEqual(stats["used_percent"], 50)
        self.assertEqual(stats["sf2_max_upload_mb"], 2048)
        self.assertEqual(stats["fluidsynth_mb"], 120)


class TestAudioUtils(unittest.TestCase):
    def test_card_from_audio_device(self):
        self.assertEqual(card_from_audio_device("plughw:1,0"), 1)
        self.assertEqual(card_from_audio_device("hw:0,0"), 0)
        self.assertEqual(card_from_audio_device("invalid"), 0)

    def test_normalize_volume(self):
        self.assertEqual(normalize_volume(0), 0)
        self.assertEqual(normalize_volume(100), 100)
        self.assertEqual(normalize_volume(127), 100)
        self.assertEqual(normalize_volume(64), 64)

    def test_volume_to_alsa_percent(self):
        self.assertEqual(volume_to_alsa_percent(0), 0)
        self.assertEqual(volume_to_alsa_percent(100), 100)
        self.assertEqual(volume_to_alsa_percent(64), 64)

    @patch("audio_utils.alsaaudio.cards")
    def test_list_playback_devices(self, mock_cards):
        mock_cards.return_value = ["Headphones", "USB Audio Device"]
        devices = list_playback_devices()
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0]["id"], "plughw:0,0")
        self.assertEqual(devices[1]["id"], "hw:1,0")
        self.assertEqual(devices[1]["sample_rate"], 48000)
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


class TestNmcliParse(unittest.TestCase):
    def test_simple_fields(self):
        self.assertEqual(parse_nmcli_terse_fields("Home:72:WPA2"), ["Home", "72", "WPA2"])

    def test_escaped_colon_in_ssid(self):
        self.assertEqual(
            parse_nmcli_terse_fields(r"Foo\:Bar:55:WPA2"),
            ["Foo:Bar", "55", "WPA2"],
        )


class TestWifiConnect(unittest.TestCase):
    @patch("wifi_utils._run")
    @patch("wifi_utils.prepare_wifi_scan")
    def test_connect_with_password(self, mock_prepare, mock_run):
        mock_prepare.return_value = (True, "ok")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, err = connect_wifi_network("MyNet", "secret123")
        self.assertTrue(ok)
        self.assertIsNone(err)
        connect_cmd = mock_run.call_args_list[-3][0][0]
        self.assertIn("device", connect_cmd)
        self.assertIn("wifi", connect_cmd)
        self.assertIn("connect", connect_cmd)
        self.assertIn("MyNet", connect_cmd)
        self.assertIn("password", connect_cmd)
        self.assertIn("secret123", connect_cmd)


class TestEventLog(unittest.TestCase):
    def test_log_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "console.log"
            os.environ["TABLOZA_CONSOLE_LOG"] = str(log_path)
            import importlib
            import event_log as el

            importlib.reload(el)
            el.clear_events()
            el.log_event("test", "hello")
            lines = el.read_events()
            self.assertEqual(len(lines), 1)
            self.assertIn("hello", lines[0])


if __name__ == "__main__":
    unittest.main()

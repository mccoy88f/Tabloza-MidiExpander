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
    alsa_device_for_card,
    apply_audio_fallback_if_needed,
    card_from_audio_device,
    list_playback_devices,
    normalize_volume,
    parse_aplay_playback,
    probe_playback_device,
    resolve_audio_device,
    volume_to_alsa_percent,
)
from event_log import clear_events, log_event, read_events  # noqa: E402
from soundfont_config import (  # noqa: E402
    coerce_default_soundfont,
    resolve_default_soundfont,
    set_default_soundfont,
    startup_soundfont_name,
)
from wifi_utils import connect_wifi_network, disable_wifi, enable_wifi, parse_nmcli_terse_fields  # noqa: E402


class TestSystemStats(unittest.TestCase):
    @patch("system_stats._read_meminfo_kb")
    @patch("system_stats._process_rss_mb")
    @patch("system_stats._read_temperature_c", return_value=52.3)
    @patch("system_stats._cpu_stats")
    @patch("system_stats._disk_stats")
    def test_get_device_stats(self, mock_disk, mock_cpu, _temp, mock_rss, mock_mem):
        mock_mem.return_value = {
            "MemTotal": 4 * 1024 * 1024,
            "MemAvailable": 2 * 1024 * 1024,
            "SwapTotal": 1024 * 1024,
            "SwapFree": 512 * 1024,
        }
        mock_rss.side_effect = lambda *a, **k: 120 if a[0] == "fluidsynth" else 40
        mock_cpu.return_value = {"percent": 33.5, "load_1m": 0.42, "cores": 4}
        mock_disk.return_value = {
            "disk_total_mb": 32000,
            "disk_used_mb": 8000,
            "disk_free_mb": 24000,
            "disk_used_percent": 25,
        }
        from system_stats import get_device_stats

        stats = get_device_stats()
        self.assertEqual(stats["total_mb"], 4096)
        self.assertEqual(stats["used_percent"], 50)
        self.assertEqual(stats["fluidsynth_mb"], 120)
        self.assertEqual(stats["disk_used_percent"], 25)
        self.assertEqual(stats["percent"], 33.5)
        self.assertEqual(stats["temperature_c"], 52.3)

    @patch("system_stats._read_meminfo_kb")
    @patch("system_stats._process_rss_mb")
    @patch("system_stats._disk_stats")
    def test_get_memory_stats(self, mock_disk, mock_rss, mock_mem):
        mock_mem.return_value = {
            "MemTotal": 4 * 1024 * 1024,
            "MemAvailable": 2 * 1024 * 1024,
            "SwapTotal": 1024 * 1024,
            "SwapFree": 512 * 1024,
        }
        mock_rss.side_effect = lambda *a, **k: 120 if a[0] == "fluidsynth" else 40
        mock_disk.return_value = {
            "disk_total_mb": 32000,
            "disk_used_mb": 8000,
            "disk_free_mb": 24000,
            "disk_used_percent": 25,
        }
        from system_stats import get_memory_stats

        stats = get_memory_stats()
        self.assertEqual(stats["total_mb"], 4096)
        self.assertEqual(stats["available_mb"], 2048)
        self.assertEqual(stats["used_mb"], 2048)
        self.assertEqual(stats["used_percent"], 50)
        self.assertEqual(stats["sf2_max_upload_mb"], 2048)
        self.assertEqual(stats["fluidsynth_mb"], 120)
        self.assertEqual(stats["disk_free_mb"], 24000)


class TestSynthConfig(unittest.TestCase):
    def test_merge_defaults_stable_preset(self):
        from synth_config import DEFAULT_AUDIO_PRESET, merge_fluidsynth_config

        fs = merge_fluidsynth_config({})
        self.assertEqual(fs["audio_preset"], DEFAULT_AUDIO_PRESET)
        self.assertEqual(fs["period_size"], 1024)
        self.assertEqual(fs["period_count"], 8)
        self.assertEqual(fs["polyphony"], 256)
        self.assertTrue(fs["reverb"])
        self.assertTrue(fs["chorus"])

    def test_parse_update_needs_restart_on_preset(self):
        from synth_config import merge_fluidsynth_config, parse_synth_settings_update

        cfg = {"fluidsynth": merge_fluidsynth_config({"audio_preset": "standard"})}
        fs, restart = parse_synth_settings_update({"audio_preset": "stable"}, cfg)
        self.assertTrue(restart)
        self.assertEqual(fs["period_size"], 1024)

    def test_parse_update_runtime_only(self):
        from synth_config import merge_fluidsynth_config, parse_synth_settings_update

        cfg = {"fluidsynth": merge_fluidsynth_config({})}
        fs, restart = parse_synth_settings_update({"reverb": False}, cfg)
        self.assertFalse(restart)
        self.assertFalse(fs["reverb"])

    def test_parse_update_needs_restart_on_polyphony(self):
        from synth_config import merge_fluidsynth_config, parse_synth_settings_update

        cfg = {"fluidsynth": merge_fluidsynth_config({})}
        fs, restart = parse_synth_settings_update({"polyphony": 512}, cfg)
        self.assertTrue(restart)
        self.assertEqual(fs["polyphony"], 512)

    def test_normalize_synth_gain(self):
        from synth_config import MAX_SYNTH_GAIN, MIN_SYNTH_GAIN, normalize_synth_gain

        self.assertEqual(normalize_synth_gain(2.0), 2.0)
        self.assertEqual(normalize_synth_gain("1.5"), 1.5)
        self.assertEqual(normalize_synth_gain(-1), MIN_SYNTH_GAIN)
        self.assertEqual(normalize_synth_gain(99), MAX_SYNTH_GAIN)


class TestMidiConfig(unittest.TestCase):
    def test_merge_defaults(self):
        from midi_config import (
            DEFAULT_MIDI_BANK_SELECT,
            DEFAULT_MIDI_JITTER_BUFFER_MS,
            merge_midi_config,
        )

        midi = merge_midi_config(None)
        self.assertEqual(midi["jitter_buffer_ms"], DEFAULT_MIDI_JITTER_BUFFER_MS)
        self.assertTrue(midi["jitter_buffer_enabled"])
        self.assertTrue(midi["rtp_midi_timestamps_enabled"])
        self.assertTrue(midi["sysex_bank_auto"])
        self.assertEqual(midi["bank_select"], DEFAULT_MIDI_BANK_SELECT)

    def test_normalize_clamps_range(self):
        from midi_config import MAX_MIDI_JITTER_BUFFER_MS, MIN_MIDI_JITTER_BUFFER_MS, normalize_jitter_buffer_ms

        self.assertEqual(normalize_jitter_buffer_ms(-5), MIN_MIDI_JITTER_BUFFER_MS)
        self.assertEqual(normalize_jitter_buffer_ms(999), MAX_MIDI_JITTER_BUFFER_MS)
        self.assertEqual(normalize_jitter_buffer_ms("40"), 40)

    def test_get_jitter_buffer_ms_from_config(self):
        from midi_config import get_jitter_buffer_ms

        self.assertEqual(get_jitter_buffer_ms({}), 25)
        self.assertEqual(get_jitter_buffer_ms({"midi": {"jitter_buffer_ms": 50}}), 50)
        self.assertEqual(get_jitter_buffer_ms({"midi": {"jitter_buffer_enabled": False}}), 0)

    def test_bank_select_normalization(self):
        from midi_config import get_midi_bank_select, normalize_bank_select

        self.assertEqual(normalize_bank_select("XG"), "xg")
        self.assertEqual(normalize_bank_select("invalid"), "gs")
        self.assertEqual(get_midi_bank_select({"midi": {"bank_select": "mma"}}), "mma")

    def test_parse_midi_settings_update(self):
        from midi_config import parse_midi_settings_update

        current = {
            "midi": {
                "bank_select": "gs",
                "jitter_buffer_enabled": True,
                "jitter_buffer_ms": 25,
                "rtp_midi_timestamps_enabled": True,
            },
        }
        midi, restart, buffer, rtpmidid = parse_midi_settings_update({"bank_select": "xg"}, current)
        self.assertEqual(midi["bank_select"], "xg")
        self.assertTrue(restart)
        self.assertFalse(buffer)
        self.assertFalse(rtpmidid)

        midi, restart, buffer, rtpmidid = parse_midi_settings_update({"jitter_buffer_enabled": False}, current)
        self.assertFalse(midi["jitter_buffer_enabled"])
        self.assertFalse(restart)
        self.assertTrue(buffer)
        self.assertFalse(rtpmidid)

        midi, restart, buffer, rtpmidid = parse_midi_settings_update(
            {"rtp_midi_timestamps_enabled": False}, current,
        )
        self.assertFalse(midi["rtp_midi_timestamps_enabled"])
        self.assertFalse(restart)
        self.assertFalse(buffer)
        self.assertTrue(rtpmidid)

    def test_render_rtpmidid_ini(self):
        from rtpmidid_config import render_rtpmidid_ini

        on = render_rtpmidid_ini(use_rtp_midi_timestamps=True, playout_buffer_ms=25)
        off = render_rtpmidid_ini(use_rtp_midi_timestamps=False, playout_buffer_ms=0)
        self.assertIn("use_rtp_midi_timestamps=true", on)
        self.assertIn("use_rtp_midi_timestamps=false", off)
        self.assertIn("name=tabloza-me", on)
        self.assertIn("playout_buffer_ms=25", on)
        self.assertIn("playout_buffer_ms=0", off)
        self.assertIn("[rtpmidi_discover]", on)
        self.assertIn("enabled=false", on)

    def test_jitter_buffer_zero_when_rtp_timestamps(self):
        from midi_config import get_jitter_buffer_ms, get_rtpmidid_playout_buffer_ms

        config = {
            "midi": {
                "jitter_buffer_enabled": True,
                "jitter_buffer_ms": 25,
                "rtp_midi_timestamps_enabled": True,
            },
        }
        self.assertEqual(get_jitter_buffer_ms(config), 0)
        self.assertEqual(get_rtpmidid_playout_buffer_ms(config), 25)

        config["midi"]["rtp_midi_timestamps_enabled"] = False
        self.assertEqual(get_jitter_buffer_ms(config), 25)
        self.assertEqual(get_rtpmidid_playout_buffer_ms(config), 0)

    def test_midi_bytes_flattens_nested_payloads(self):
        from midi_jitter_buffer import MidiGateway

        gw = MidiGateway(25)
        self.assertEqual(gw._midi_bytes((144, 60, 100)), [144, 60, 100])
        self.assertEqual(gw._midi_bytes([[144, 60, 100]]), [144, 60, 100])
        self.assertEqual(gw._midi_bytes(([144, 60, 100],)), [144, 60, 100])
        self.assertEqual(gw._midi_bytes(bytes([144, 60, 100])), [144, 60, 100])
        self.assertEqual(gw._split_midi_messages([0, 0, 144, 60, 100]), [[144, 60, 100]])
        self.assertEqual(
            gw._split_midi_messages([144, 60, 100, 128, 60, 64]),
            [[144, 60, 100], [128, 60, 64]],
        )
        self.assertFalse(gw._is_forwardable([0xFF, 0x51, 0x03, 0x07]))
        self.assertTrue(gw._is_forwardable([0x90, 0x3C, 0x64]))
        # SMF/aplaymidi: spurious 0x00 after PC must not become prog 0 on same channel.
        self.assertEqual(
            gw._split_midi_messages([0xC6, 0x19, 0x00, 0xB6, 0x07, 0x4D]),
            [[0xC6, 0x19], [0xB6, 0x07, 0x4D]],
        )

    @patch("midi_jitter_buffer.is_usable_python_rtmidi", return_value=False)
    def test_ensure_gateway_without_rtmidi(self, _usable):
        from midi_jitter_buffer import ensure_midi_gateway, jitter_buffer_status

        self.assertFalse(ensure_midi_gateway(0, sysex_auto=True))
        self.assertFalse(jitter_buffer_status()["active"])

    def test_route_destination_prefers_buffer(self):
        from midi_utils import _route_destination

        buf_port = {"client": "Tabloza Buffer", "name": "Tabloza Buffer", "address": "129:0"}
        fs_port = {"client": "FLUID Synth", "name": "Synth input port", "address": "128:0"}
        with patch("midi_jitter_buffer.get_buffer_input_port", return_value=buf_port):
            with patch("midi_utils.find_fluidsynth_input", return_value=fs_port):
                self.assertEqual(_route_destination(), buf_port)

    def test_is_buffer_input_port_rtmidi_client(self):
        from midi_jitter_buffer import _is_buffer_input_port

        port = {
            "client": "RtMidiIn Client",
            "name": "Tabloza Buffer  ",
            "address": "130:0",
        }
        self.assertTrue(_is_buffer_input_port(port))


class TestMidiSysexMode(unittest.TestCase):
    def test_detect_gm_system_on(self):
        from midi_sysex_mode import detect_bank_mode_from_sysex

        payload = bytes([0x7E, 0x7F, 0x09, 0x01])
        self.assertEqual(detect_bank_mode_from_sysex(payload), "gm")

    def test_detect_gm2_system_on_maps_mma(self):
        from midi_sysex_mode import detect_bank_mode_from_sysex

        payload = bytes([0x7E, 0x7F, 0x09, 0x03])
        self.assertEqual(detect_bank_mode_from_sysex(payload), "mma")

    def test_detect_gs_mode_set(self):
        from midi_sysex_mode import detect_bank_mode_from_sysex

        payload = bytes([0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41])
        self.assertEqual(detect_bank_mode_from_sysex(payload), "gs")

    def test_detect_xg_reset(self):
        from midi_sysex_mode import detect_bank_mode_from_sysex

        payload = bytes([0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00])
        self.assertEqual(detect_bank_mode_from_sysex(payload), "xg")

    @patch("fluidsynth_client.shell_bound", return_value=True)
    @patch("fluidsynth_client.send_command", return_value=(True, "ok"))
    def test_maybe_apply_consumes_mode_sysex(self, mock_send, _bound):
        from midi_sysex_mode import maybe_apply_sysex_bank_mode, reset_runtime_bank_select

        reset_runtime_bank_select("gs")
        msg = (0xF0, 0x7E, 0x7F, 0x09, 0x01, 0xF7)
        self.assertTrue(maybe_apply_sysex_bank_mode(msg))
        mock_send.assert_any_call("set synth.midi-bank-select gm")
        reset_calls = [c for c in mock_send.call_args_list if c[0][0] == "reset"]
        self.assertEqual(reset_calls, [])

    def test_non_mode_sysex_not_consumed(self):
        from midi_sysex_mode import maybe_apply_sysex_bank_mode

        msg = (0xF0, 0x7E, 0x7F, 0x08, 0x01, 0xF7)
        self.assertFalse(maybe_apply_sysex_bank_mode(msg))


class TestSf2LoadProgress(unittest.TestCase):
    @patch("system_stats.fluidsynth_rss_mb", return_value=150)
    def test_estimate_progress_from_ram(self, _rss):
        from fluidsynth_client import estimate_sf2_load_progress

        self.assertEqual(estimate_sf2_load_progress(100.0, 200.0), 25)
        self.assertEqual(estimate_sf2_load_progress(100.0, 100.0), 50)

    @patch("system_stats.fluidsynth_rss_mb", return_value=500)
    def test_estimate_progress_caps_at_99(self, _rss):
        from fluidsynth_client import estimate_sf2_load_progress

        self.assertEqual(estimate_sf2_load_progress(100.0, 200.0), 99)

    @patch("system_stats.fluidsynth_rss_mb", return_value=None)
    def test_estimate_progress_without_rss(self, _rss):
        from fluidsynth_client import estimate_sf2_load_progress

        self.assertEqual(estimate_sf2_load_progress(100.0, 200.0), 0)


class TestRtmidiCompat(unittest.TestCase):
    def test_alsa_api_prefers_linux_constant(self):
        import rtmidi_compat as rc

        class FakeRtmidi:
            API_LINUX_ALSA = 7

        with patch.object(rc, "rtmidi", FakeRtmidi()):
            self.assertEqual(rc.alsa_rtmidi_api(), 7)

    def test_is_usable_with_open_virtual_port(self):
        import rtmidi_compat as rc

        class FakeIn:
            def open_virtual_port(self, _name):
                return None

        class FakeRtmidi:
            def MidiIn(self):
                return FakeIn()

            def MidiOut(self):
                return object()

        with patch.object(rc, "rtmidi", FakeRtmidi()):
            self.assertTrue(rc.is_usable_python_rtmidi())

    def test_diagnostic_for_wrong_package(self):
        import rtmidi_compat as rc

        class FakeRtmidi:
            __file__ = "/usr/lib/python3/dist-packages/rtmidi/__init__.py"

            class MidiIn:
                pass

            class MidiOut:
                pass

        with patch.object(rc, "rtmidi", FakeRtmidi()):
            self.assertFalse(rc.is_usable_python_rtmidi())
            self.assertIn("non compatibile", rc.rtmidi_diagnostic())

    def test_configure_midi_in_without_active_sensing_kw(self):
        from rtmidi_compat import configure_midi_in

        calls = []

        class FakeIn:
            def ignore_types(self, *args, **kwargs):
                calls.append((args, kwargs))
                if "active_sensing" in kwargs:
                    raise TypeError("unexpected keyword argument 'active_sensing'")

        configure_midi_in(FakeIn())
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1], {"sysex": False, "timing": False})


class TestActivityStatus(unittest.TestCase):
    def test_aseqdump_event_lines(self):
        from activity_status import is_aseqdump_midi_event

        self.assertTrue(is_aseqdump_midi_event(" 23:01:23.045  24:0   Note on               0, note 60, velocity 100"))
        self.assertTrue(is_aseqdump_midi_event("128:0   Control change          0, controller 7, value 100"))
        self.assertTrue(is_aseqdump_midi_event("128:0   Program change          0, program 1"))
        self.assertFalse(is_aseqdump_midi_event("Waiting for events at port 128:0"))
        self.assertFalse(is_aseqdump_midi_event("Source  Event                   Ch Ch"))
        self.assertFalse(is_aseqdump_midi_event(""))

    def test_midi_active_window(self):
        from activity_status import MIDI_ACTIVE_WINDOW_SEC

        self.assertGreaterEqual(MIDI_ACTIVE_WINDOW_SEC, 5.0)


class TestMidiMonitorPort(unittest.TestCase):
    @patch("midi_utils.find_usb_midi_outputs")
    @patch("midi_utils.find_rtpmidid_outputs")
    @patch("midi_utils.get_active_routes")
    @patch("midi_utils.find_fluidsynth_input")
    def test_monitor_command_all_when_routes_exist(self, mock_fs, mock_routes, mock_rtp, mock_usb):
        from midi_utils import midi_monitor_command, midi_monitor_port

        mock_routes.return_value = [{"from": "128:1", "to": "129:0"}]
        cmd, key = midi_monitor_command()
        self.assertEqual(cmd, ["aseqdump"])
        self.assertEqual(key, "tap")
        port, port_key = midi_monitor_port()
        self.assertEqual(port, "tap")
        self.assertEqual(port_key, "tap")
        mock_fs.assert_not_called()

    @patch("midi_utils.find_usb_midi_outputs")
    @patch("midi_utils.find_rtpmidid_outputs")
    @patch("midi_utils.get_active_routes")
    @patch("midi_utils.find_fluidsynth_input")
    def test_monitor_command_all_when_rtpmidid_present(self, mock_fs, mock_routes, mock_rtp, mock_usb):
        from midi_utils import midi_monitor_command

        mock_routes.return_value = []
        mock_rtp.return_value = [{"address": "128:1", "client": "rtpmidid", "name": "Mac"}]
        mock_usb.return_value = []
        cmd, key = midi_monitor_command()
        self.assertEqual(cmd, ["aseqdump"])
        self.assertEqual(key, "tap")

    @patch("midi_utils.find_usb_midi_outputs")
    @patch("midi_utils.find_rtpmidid_outputs")
    @patch("midi_utils.get_active_routes")
    @patch("midi_utils.find_fluidsynth_input")
    def test_monitor_command_tap_when_only_fluidsynth(self, mock_fs, mock_routes, mock_rtp, mock_usb):
        from midi_utils import midi_monitor_command

        mock_routes.return_value = []
        mock_rtp.return_value = []
        mock_usb.return_value = []
        mock_fs.return_value = {"address": "128:0"}
        cmd, key = midi_monitor_command()
        self.assertEqual(cmd, ["aseqdump"])
        self.assertEqual(key, "tap")

    @patch("midi_utils.find_usb_midi_outputs")
    @patch("midi_utils.find_rtpmidid_outputs")
    @patch("midi_utils.get_active_routes")
    @patch("midi_utils.find_fluidsynth_input")
    def test_none_without_ports(self, mock_fs, mock_routes, mock_rtp, mock_usb):
        from midi_utils import midi_monitor_command

        mock_routes.return_value = []
        mock_rtp.return_value = []
        mock_usb.return_value = []
        mock_fs.return_value = None
        cmd, key = midi_monitor_command()
        self.assertEqual(cmd, [])
        self.assertIsNone(key)


class TestMidiMonitorTap(unittest.TestCase):
    @patch("midi_utils.get_input_ports")
    def test_find_aseqdump_input(self, mock_ports):
        from midi_utils import find_aseqdump_input

        mock_ports.return_value = [
            {"client": "aseqdump", "name": "Input", "address": "130:0"},
        ]
        port = find_aseqdump_input()
        self.assertEqual(port["address"], "130:0")

    @patch("midi_utils.subprocess.run")
    @patch("midi_utils._midi_sources_for_routing")
    def test_refresh_midi_monitor_tap(self, mock_sources, mock_run):
        from midi_utils import refresh_midi_monitor_tap, set_midi_monitor_input

        set_midi_monitor_input(None)
        self.assertEqual(refresh_midi_monitor_tap(), 0)
        set_midi_monitor_input("130:0")
        mock_sources.return_value = [
            {"address": "128:1", "client": "rtpmidid"},
            {"address": "128:2", "client": "rtpmidid"},
        ]
        self.assertEqual(refresh_midi_monitor_tap(), 2)
        calls = [c.args[0] for c in mock_run.call_args_list]
        self.assertEqual(calls[0], ["aconnect", "128:1", "130:0"])
        self.assertEqual(calls[1], ["aconnect", "128:2", "130:0"])
        set_midi_monitor_input(None)


class TestMidiRouting(unittest.TestCase):
    def test_dedupe_rtpmidid_outputs(self):
        from midi_utils import _dedupe_rtpmidid_outputs

        sources = [
            {"address": "128:1", "client": "rtpmidid", "name": "MacBook Air"},
            {"address": "128:2", "client": "rtpmidid", "name": "MacBook Air"},
            {"address": "128:3", "client": "rtpmidid", "name": "Other Host"},
        ]
        deduped = _dedupe_rtpmidid_outputs(sources)
        self.assertEqual([p["address"] for p in deduped], ["128:1", "128:3"])

    @patch("midi_utils.subprocess.run")
    def test_disconnect_source_routes(self, mock_run):
        from midi_utils import disconnect_source_routes

        mock_run.return_value = MagicMock(stdout=(
            "client 14: 'rtpmidid' [type=user]\n"
            "    0 'Network'\n"
            "        Connecting To: 128:0\n"
        ))
        with patch("midi_utils._aconnect_list_output", return_value=mock_run.return_value.stdout):
            removed = disconnect_source_routes("14:0")
        self.assertEqual(removed, 1)
        mock_run.assert_called()

    def test_is_midi_connected(self):
        from midi_utils import is_midi_connected

        listing = (
            "client 128: 'rtpmidid' [type=user]\n"
            "    1 'Mac'\n"
            "        Connecting To: 130:0\n"
        )
        with patch("midi_utils._aconnect_list_output", return_value=listing):
            self.assertTrue(is_midi_connected("128:1", "130:0"))
            self.assertFalse(is_midi_connected("128:1", "129:0"))
    def test_save_config_merges_fluidsynth_fields(self):
        import json
        import sys
        from unittest.mock import MagicMock

        sys.modules.setdefault("bcrypt", MagicMock())
        import tabloza_common as tc

        with tempfile.TemporaryDirectory() as td:
            config_file = Path(td) / "config.json"
            config_file.write_text(json.dumps({
                "volume": 80,
                "fluidsynth": {
                    "polyphony": 512,
                    "audio_preset": "standard",
                    "audio_device": "plughw:0,0",
                },
            }))
            with patch.object(tc, "CONFIG_FILE", config_file):
                tc.save_config({
                    "fluidsynth": {
                        "audio_device": "plughw:1,0",
                        "alsa_card": 1,
                    },
                })
                saved = json.loads(config_file.read_text())
                self.assertEqual(saved["volume"], 80)
                self.assertEqual(saved["fluidsynth"]["polyphony"], 512)
                self.assertEqual(saved["fluidsynth"]["audio_device"], "plughw:1,0")
                self.assertEqual(saved["fluidsynth"]["alsa_card"], 1)


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

    def test_alsa_device_hdmi_uses_plughw(self):
        self.assertEqual(alsa_device_for_card(2, 0, "vc4hdmi0"), "plughw:2,0")
        self.assertEqual(alsa_device_for_card(1, 0, "USB AUDIO"), "hw:1,0")
        self.assertEqual(alsa_device_for_card(0, 0, "Headphones"), "plughw:0,0")

    def test_resolve_audio_device_hdmi(self):
        with patch("audio_utils._card_names", return_value=["Headphones", "USB", "vc4hdmi0"]):
            self.assertEqual(resolve_audio_device("hw:2,0"), "plughw:2,0")

    def test_parse_aplay_playback_hdmi(self):
        sample = """
**** List of PLAYBACK Hardware Devices ****
card 0: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
card 1: vc4hdmi0 [vc4-hdmi-0], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]
card 2: vc4hdmi1 [vc4-hdmi-1], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]
"""
        entries = parse_aplay_playback(sample)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[1][:3], (1, 0, "vc4hdmi0"))
        self.assertEqual(entries[2][:3], (2, 0, "vc4hdmi1"))

    @patch("audio_utils._playback_entries_from_aplay", return_value=None)
    @patch("audio_utils.alsaaudio.cards")
    def test_list_playback_devices(self, mock_cards, _aplay):
        mock_cards.return_value = ["Headphones", "USB Audio Device", "vc4hdmi0"]
        devices = list_playback_devices()
        self.assertEqual(len(devices), 3)
        self.assertEqual(devices[0]["id"], "plughw:0,0")
        self.assertEqual(devices[1]["id"], "hw:1,0")
        self.assertEqual(devices[1]["sample_rate"], 48000)
        self.assertEqual(devices[2]["id"], "plughw:2,0")
        self.assertIn("vc4hdmi0", devices[2]["name"])

    @patch("audio_utils._playback_entries_from_aplay")
    def test_list_playback_devices_from_aplay(self, mock_aplay):
        mock_aplay.return_value = [
            (0, 0, "Headphones", "bcm2835 Headphones"),
            (1, 0, "vc4hdmi0", "MAI PCM i2s-hifi-0"),
            (2, 0, "vc4hdmi1", "MAI PCM i2s-hifi-0"),
        ]
        devices = list_playback_devices()
        self.assertEqual(len(devices), 3)
        self.assertEqual(devices[1]["id"], "plughw:1,0")
        self.assertIn("vc4hdmi1", devices[2]["name"])

    @patch("audio_utils._open_playback_pcm")
    def test_probe_playback_device_open_fails(self, mock_open):
        import alsaaudio
        mock_open.side_effect = alsaaudio.ALSAAudioError("No such device")
        ok, err = probe_playback_device("plughw:2,0")
        self.assertFalse(ok)
        self.assertIn("No such device", err or "")

    @patch("audio_utils.probe_playback_device", return_value=(False, "busy"))
    def test_apply_audio_fallback_if_needed(self, _probe):
        config = {"fluidsynth": {"audio_device": "plughw:2,0", "alsa_card": 2}}
        updated, changed, msg = apply_audio_fallback_if_needed(config)
        self.assertFalse(changed)
        self.assertEqual(updated, config)
        self.assertEqual(msg, "")


class TestFluidSynthClient(unittest.TestCase):
    def test_parse_font_ids_from_log(self):
        from fluidsynth_client import parse_font_ids_from_log

        text = "\n".join([
            "ID Name",
            "2 Uplift.sf2",
            "1 /var/lib/tabloza/soundfonts/FluidR3_GM.sf2",
        ])
        self.assertEqual(parse_font_ids_from_log(text), [2, 1])

    def test_parse_fonts_from_log(self):
        from fluidsynth_client import parse_fonts_from_log

        text = "\n".join([
            "ID Name",
            "1 /var/lib/tabloza/soundfonts/SD1000.sf2",
        ])
        fonts = parse_fonts_from_log(text)
        self.assertEqual(len(fonts), 1)
        self.assertEqual(fonts[0]["path"], "/var/lib/tabloza/soundfonts/SD1000.sf2")

    def test_soundfont_path_matches(self):
        from fluidsynth_client import soundfont_path_matches

        path = Path("/var/lib/tabloza/soundfonts/SD1000.sf2")
        self.assertTrue(soundfont_path_matches(path, "/var/lib/tabloza/soundfonts/SD1000.sf2"))
        self.assertTrue(soundfont_path_matches(path, "SD1000.sf2"))
        self.assertFalse(soundfont_path_matches(path, "Other.sf2"))

    def test_parse_load_error_from_log(self):
        from fluidsynth_client import parse_load_error_from_log

        text = 'fluidsynth: error: Failed to load SoundFont "/tmp/x.sf2"'
        self.assertIn("Failed to load", parse_load_error_from_log(text))

    def test_parse_font_ids_empty(self):
        from fluidsynth_client import parse_font_ids_from_log

        self.assertEqual(parse_font_ids_from_log("No SoundFont loaded"), [])

    @patch("fluidsynth_client._shell_stdin", object())
    @patch("fluidsynth_client.send_command", return_value=(True, "ok"))
    @patch("fluidsynth_client.query_loaded_font_ids")
    @patch("fluidsynth_client.time.sleep")
    def test_unload_all_soundfonts(self, _sleep, mock_ids, mock_send):
        from fluidsynth_client import unload_all_soundfonts

        mock_ids.side_effect = [[2, 1], []]
        ok, detail = unload_all_soundfonts(lambda: True)
        self.assertTrue(ok)
        self.assertEqual(detail, "unloaded")
        sent = [call.args[0] for call in mock_send.call_args_list]
        self.assertIn("unload 2", sent)
        self.assertIn("unload 1", sent)
        self.assertIn("reset", sent)

    @patch("system_stats.fluidsynth_rss_mb", return_value=10)
    @patch("fluidsynth_client.write_soundfont_state")
    @patch("fluidsynth_client.unload_all_soundfonts", return_value=(True, "unloaded"))
    @patch("fluidsynth_client.is_path_in_loaded_fonts", return_value=True)
    @patch("fluidsynth_client.query_loaded_fonts", return_value=[{"id": 1, "path": "x.sf2"}])
    @patch("fluidsynth_client._wait_for_load_completion", return_value=(True, None))
    @patch("fluidsynth_client.send_command", return_value=(True, "ok"))
    @patch("fluidsynth_client.time.sleep")
    def test_load_soundfont_verified(self, _sleep, _send, _wait, _fonts, _match, _unload, _write, _rss):
        from fluidsynth_client import load_soundfont

        sf = Path("/tmp/tabloza-test-load.sf2")
        sf.write_bytes(b"x")
        try:
            ok, detail = load_soundfont(sf, lambda: True)
            self.assertTrue(ok)
            self.assertEqual(detail, "loaded")
        finally:
            sf.unlink(missing_ok=True)

    @patch("system_stats.fluidsynth_rss_mb", return_value=10)
    @patch("fluidsynth_client.write_soundfont_state")
    @patch("fluidsynth_client.unload_all_soundfonts", return_value=(True, "unloaded"))
    @patch("fluidsynth_client.is_path_in_loaded_fonts", return_value=True)
    @patch("fluidsynth_client.query_loaded_fonts", return_value=[{"id": 1, "path": "x.sf2"}])
    @patch("fluidsynth_client._wait_for_load_completion", return_value=(True, None))
    @patch("fluidsynth_client.send_command", return_value=(True, "ok"))
    @patch("fluidsynth_client.time.sleep")
    def test_load_soundfont_quotes_path_with_spaces(self, _sleep, mock_send, _wait, _fonts, _match, _unload, _write, _rss):
        from fluidsynth_client import load_soundfont

        sf = Path("/tmp/SD1000 Sound Family Map.sf2")
        sf.write_bytes(b"x")
        try:
            ok, detail = load_soundfont(sf, lambda: True)
            self.assertTrue(ok)
            load_cmd = next(c.args[0] for c in mock_send.call_args_list if c.args[0].startswith("load "))
            self.assertIn("SD1000 Sound Family Map.sf2", load_cmd)
            self.assertTrue("'" in load_cmd or '"' in load_cmd)
        finally:
            sf.unlink(missing_ok=True)

    @patch("system_stats.fluidsynth_rss_mb", return_value=10)
    @patch("fluidsynth_client.write_soundfont_state")
    @patch("fluidsynth_client.unload_all_soundfonts", return_value=(True, "unloaded"))
    @patch("fluidsynth_client.is_path_in_loaded_fonts", return_value=False)
    @patch("fluidsynth_client.query_loaded_fonts", return_value=[])
    @patch("fluidsynth_client._wait_for_load_completion", return_value=(True, None))
    @patch("fluidsynth_client.send_command", return_value=(True, "ok"))
    @patch("fluidsynth_client.time.sleep")
    def test_load_soundfont_not_in_stack_fails(self, _sleep, _send, _wait, _fonts, _match, _unload, _write, _rss):
        from fluidsynth_client import load_soundfont

        sf = Path("/tmp/tabloza-test-missing.sf2")
        sf.write_bytes(b"x")
        try:
            ok, detail = load_soundfont(sf, lambda: True)
            self.assertFalse(ok)
            self.assertIn("non presente in FluidSynth", detail)
        finally:
            sf.unlink(missing_ok=True)

    @patch("system_stats.fluidsynth_rss_mb", return_value=10)
    @patch("fluidsynth_client.write_soundfont_state")
    @patch("fluidsynth_client.unload_all_soundfonts", return_value=(True, "unloaded"))
    @patch("fluidsynth_client._wait_for_load_completion", return_value=(False, "failed to load"))
    @patch("fluidsynth_client.send_command", return_value=(True, "ok"))
    @patch("fluidsynth_client.time.sleep")
    def test_load_soundfont_log_error_fails(self, _sleep, _send, _wait, _unload, _write, _rss):
        from fluidsynth_client import load_soundfont

        sf = Path("/tmp/tabloza-test-error.sf2")
        sf.write_bytes(b"x")
        try:
            ok, detail = load_soundfont(sf, lambda: True)
            self.assertFalse(ok)
            self.assertIn("Caricamento fallito", detail)
        finally:
            sf.unlink(missing_ok=True)

    @patch("system_stats.fluidsynth_rss_mb", return_value=10)
    @patch("fluidsynth_client.write_soundfont_state")
    @patch("fluidsynth_client.unload_all_soundfonts", return_value=(True, "unloaded"))
    @patch("fluidsynth_client.is_path_in_loaded_fonts", return_value=True)
    @patch("fluidsynth_client.query_loaded_fonts", return_value=[{"id": 1, "path": "x.sf2"}])
    @patch("fluidsynth_client._wait_for_load_completion", return_value=(True, None))
    @patch("fluidsynth_client.send_command", return_value=(True, "ok"))
    @patch("fluidsynth_client.time.sleep")
    def test_load_soundfont_cancelled_during_wait(self, _sleep, _send, _wait, _fonts, _match, _unload, _write, _rss):
        from fluidsynth_client import load_soundfont

        sf = Path("/tmp/tabloza-test-cancel.sf2")
        sf.write_bytes(b"x")
        try:
            calls = {"n": 0}

            def should_cancel():
                calls["n"] += 1
                return calls["n"] > 1

            ok, detail = load_soundfont(
                sf,
                lambda: True,
                should_cancel=should_cancel,
            )
            self.assertFalse(ok)
            self.assertEqual(detail, "cancelled")
        finally:
            sf.unlink(missing_ok=True)


class TestStartupSoundfont(unittest.TestCase):
    def test_coerce_default_soundfont(self):
        self.assertEqual(coerce_default_soundfont("a.sf2"), "a.sf2")
        self.assertEqual(coerce_default_soundfont(["b.sf2", "c.sf2"]), "b.sf2")
        self.assertEqual(coerce_default_soundfont([]), "")
        self.assertEqual(coerce_default_soundfont(None), "")

    def test_set_default_soundfont_replaces_previous(self):
        config = {"default_soundfont": "old.sf2", "active_soundfont": "x.sf2"}
        updated = set_default_soundfont(config, "new.sf2")
        self.assertEqual(updated["default_soundfont"], "new.sf2")
        self.assertEqual(resolve_default_soundfont({"default_soundfont": ["a.sf2", "b.sf2"]}), "")

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
    def setUp(self):
        import importlib
        import wifi_utils as wu

        self.lock_dir = tempfile.mkdtemp()
        self.lock_path = os.path.join(self.lock_dir, "wifi-connecting")
        os.environ["TABLOZA_WIFI_CONNECT_LOCK"] = self.lock_path
        importlib.reload(wu)
        self.wu = wu

    def tearDown(self):
        import importlib
        import wifi_utils as wu

        os.environ.pop("TABLOZA_WIFI_CONNECT_LOCK", None)
        importlib.reload(wu)
        if os.path.isfile(self.lock_path):
            os.unlink(self.lock_path)

    @patch("wifi_utils._connect_via_device_wifi")
    @patch("wifi_utils._ssid_visible", return_value=True)
    @patch("wifi_utils._ensure_wlan_client_ready")
    @patch("wifi_utils._run")
    @patch("wifi_utils.prepare_wifi_scan")
    def test_connect_with_password(self, mock_prepare, mock_run, _ready, _visible, mock_device):
        mock_prepare.return_value = (True, "ok")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_device.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, err = self.wu.connect_wifi_network("MyNet", "secret123", "WPA2")
        self.assertTrue(ok)
        self.assertIsNone(err)
        mock_device.assert_called_once_with("MyNet", "secret123", "tabloza-wifi-MyNet")

    @patch("wifi_utils.prepare_wifi_scan")
    def test_connect_secured_without_password(self, mock_prepare):
        mock_prepare.return_value = (True, "ok")
        ok, err = self.wu.connect_wifi_network("MyNet", "", "WPA2")
        self.assertFalse(ok)
        self.assertIn("Password", err or "")

    @patch("wifi_utils._connection_up")
    @patch("wifi_utils._ssid_visible", return_value=True)
    @patch("wifi_utils._ensure_wlan_client_ready")
    @patch("wifi_utils._run")
    @patch("wifi_utils.prepare_wifi_scan")
    def test_connect_open_network(self, mock_prepare, mock_run, _ready, _visible, mock_up):
        mock_prepare.return_value = (True, "ok")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_up.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, err = self.wu.connect_wifi_network("OpenNet", "", "")
        self.assertTrue(ok)
        cmds = [c[0][0] for c in mock_run.call_args_list]
        add_cmd = next(c for c in cmds if "add" in c)
        self.assertIn("wifi-sec.key-mgmt", add_cmd)
        self.assertIn("none", add_cmd)

    def test_friendly_timeout_error(self):
        msg = self.wu._friendly_connect_error("Error: Timeout expired (45 seconds)")
        self.assertIn("Timeout", msg)
        self.assertIn("90s", msg)


class TestWifiPower(unittest.TestCase):
    @patch("wifi_utils._wlan_device_present", return_value=True)
    @patch("wifi_utils._active_wifi_connection", return_value="tabloza-wifi-Home")
    @patch("wifi_utils._run")
    def test_disable_wifi(self, mock_run, _conn, _wlan):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, err = disable_wifi()
        self.assertTrue(ok)
        self.assertIsNone(err)
        radio_off = any(
            call.args[0][:4] == ["nmcli", "radio", "wifi", "off"]
            for call in mock_run.call_args_list
        )
        self.assertTrue(radio_off)

    @patch("wifi_utils._wlan_device_present", return_value=False)
    def test_disable_wifi_no_wlan(self, _wlan):
        ok, err = disable_wifi()
        self.assertFalse(ok)
        self.assertIn("wlan0", err or "")

    @patch("wifi_utils._wlan_device_present", return_value=True)
    @patch("wifi_utils._run")
    def test_enable_wifi(self, mock_run, _wlan):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, err = enable_wifi()
        self.assertTrue(ok)
        cmds = [c.args[0] for c in mock_run.call_args_list]
        self.assertIn(["nmcli", "radio", "wifi", "on"], cmds)
        self.assertIn(["nmcli", "device", "wifi", "rescan"], cmds)


class TestUpdateUtils(unittest.TestCase):
    def setUp(self):
        import update_utils as uu

        self.uu = uu
        self.tmp = tempfile.TemporaryDirectory()
        self.install = Path(self.tmp.name) / "tabloza"
        self.install.mkdir()
        (self.install / ".git").mkdir()
        (self.install / "VERSION").write_text("1.0.0")
        self.status = Path(self.tmp.name) / "update_status.json"
        self.uu.INSTALL_DIR = self.install
        self.uu.UPDATE_STATUS_FILE = self.status

    def tearDown(self):
        self.tmp.cleanup()

    @patch("update_utils._run_git")
    def test_check_no_update(self, mock_git):
        mock_git.side_effect = [
            MagicMock(returncode=0),  # fetch
            MagicMock(returncode=0, stdout="abc123\n"),  # local
            MagicMock(returncode=0, stdout="abc123\n"),  # remote
            MagicMock(returncode=0, stdout="1.0.0\n"),  # version HEAD
            MagicMock(returncode=0, stdout="1.0.0\n"),  # version origin
        ]
        result = self.uu.check_for_update(fetch=True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["update_available"])
        self.assertEqual(result["current_version"], "1.0.0")

    @patch("update_utils._run_git")
    def test_check_update_available(self, mock_git):
        mock_git.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout="aaa\n"),
            MagicMock(returncode=0, stdout="bbb\n"),
            MagicMock(returncode=0, stdout="1.0.0\n"),
            MagicMock(returncode=0, stdout="1.1.0\n"),
        ]
        result = self.uu.check_for_update(fetch=True)
        self.assertTrue(result["update_available"])
        self.assertEqual(result["remote_version"], "1.1.0")

    @patch("update_utils.subprocess.run")
    @patch("update_utils._run_git")
    def test_apply_skips_when_up_to_date(self, mock_git, mock_run):
        mock_git.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout="same\n"),
            MagicMock(returncode=0, stdout="same\n"),
            MagicMock(returncode=0, stdout="1.0.0\n"),
            MagicMock(returncode=0, stdout="1.0.0\n"),
        ]
        result = self.uu.apply_update_if_needed()
        self.assertTrue(result["ok"])
        self.assertFalse(result["applied"])
        self.assertTrue(result["up_to_date"])
        mock_run.assert_not_called()

    @patch("update_utils.subprocess.run")
    @patch("update_utils._run_git")
    def test_apply_runs_script_when_update_available(self, mock_git, mock_run):
        script = self.install / "tabloza-update.sh"
        script.write_text("#!/bin/bash\n")
        script.chmod(0o755)
        self.uu.UPDATE_SCRIPT = script

        def git_side_effect(args, *a, **k):
            if args == ["fetch", "origin", "main"]:
                return MagicMock(returncode=0)
            if args == ["rev-parse", "HEAD"]:
                return MagicMock(returncode=0, stdout="old\n")
            if args == ["rev-parse", "origin/main"]:
                return MagicMock(returncode=0, stdout="new\n")
            if args == ["show", "HEAD:VERSION"]:
                return MagicMock(returncode=0, stdout="1.0.0\n")
            if args == ["show", "origin/main:VERSION"]:
                return MagicMock(returncode=0, stdout="1.1.0\n")
            return MagicMock(returncode=0, stdout="")

        mock_git.side_effect = git_side_effect
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = self.uu.apply_update_if_needed()

        self.assertTrue(result["applied"])
        mock_run.assert_called_once_with(
            [str(script)],
            capture_output=True,
            text=True,
            timeout=self.uu.APPLY_TIMEOUT,
            check=False,
        )


class TestLanDirect(unittest.TestCase):
    @patch("network_utils._run")
    def test_start_lan_direct(self, mock_run):
        import network_utils as nu

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="eth0:ethernet\n"),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]
        ok, err = nu.start_lan_direct()
        self.assertTrue(ok)
        add_cmd = mock_run.call_args_list[3][0][0]
        self.assertIn("shared", add_cmd)
        self.assertIn("192.168.5.1/24", add_cmd)

    @patch("network_utils._write_carrier_since")
    @patch("network_utils.start_lan_direct")
    @patch("network_utils._ensure_dhcp_on_device")
    @patch("network_utils._read_carrier_since", return_value=None)
    @patch("network_utils._ethernet_carrier_up", return_value=True)
    @patch("network_utils.has_usable_eth_ip", return_value=False)
    @patch("network_utils.is_lan_direct_active", return_value=False)
    @patch("network_utils.get_primary_ethernet_device", return_value="eth0")
    def test_manage_waits_dhcp_first(self, *_mocks):
        import network_utils as nu

        nu.manage_ethernet_auto()
        nu._ensure_dhcp_on_device.assert_called_once_with("eth0")
        nu.start_lan_direct.assert_not_called()

    @patch("network_utils.start_lan_direct")
    @patch("network_utils._ensure_dhcp_on_device")
    @patch("network_utils._read_carrier_since")
    @patch("network_utils._ethernet_carrier_up", return_value=True)
    @patch("network_utils.has_usable_eth_ip", return_value=False)
    @patch("network_utils.is_lan_direct_active", return_value=False)
    @patch("network_utils.get_primary_ethernet_device", return_value="eth0")
    def test_manage_starts_router_after_grace(self, *_mocks):
        import network_utils as nu
        import time

        nu._read_carrier_since.return_value = time.time() - 60
        nu.manage_ethernet_auto()
        nu.start_lan_direct.assert_called_once()


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


class TestNetworkIps(unittest.TestCase):
    @patch("network_utils._eth_ipv4_addresses")
    def test_get_usable_ipv4_skips_link_local(self, mock_addrs):
        import network_utils as nu

        mock_addrs.return_value = ["169.254.1.2", "192.168.178.143"]
        self.assertEqual(nu.get_usable_ipv4("eth0"), "192.168.178.143")

    @patch("network_utils.get_usable_ipv4")
    @patch("network_utils.get_primary_ethernet_device")
    @patch("wifi_utils._wlan_device_present", return_value=True)
    @patch("wifi_utils._wlan_state", return_value="connected")
    @patch("wifi_utils._active_wifi_ssid", return_value="CasaMesserangeli")
    @patch("wifi_utils._active_wifi_connection", return_value="tabloza-wifi-CasaMesserangeli")
    @patch("wifi_utils._eth_connected", return_value=True)
    @patch("network_utils.is_lan_direct_active", return_value=False)
    def test_get_network_status_dual_ips(
        self, _lan, _eth, _wifi_conn, _wifi_ssid, _wlan, _wlan_dev, mock_eth_dev, mock_ipv4,
    ):
        import wifi_utils as wu

        mock_eth_dev.return_value = "eth0"

        def ipv4_side(device):
            return "192.168.178.143" if device == "eth0" else "192.168.178.50"

        mock_ipv4.side_effect = ipv4_side
        status = wu.get_network_status()
        self.assertEqual(status["network_mode"], "lan_wifi")
        self.assertEqual(status["eth_ip"], "192.168.178.143")
        self.assertEqual(status["wifi_ip"], "192.168.178.50")
        self.assertEqual(status["wifi_connection"], "CasaMesserangeli")
        self.assertEqual(status["wifi_profile"], "tabloza-wifi-CasaMesserangeli")


class TestUsbMidi(unittest.TestCase):
    @patch("midi_utils.get_output_ports")
    def test_find_usb_midi_outputs_excludes_system_clients(self, mock_ports):
        import midi_utils as mu

        mock_ports.return_value = [
            {"client": "USB MIDI Interface", "name": "USB MIDI Interface MIDI 1", "address": "24:0"},
            {"client": "FLUID Synth", "name": "Synth input port", "address": "128:0"},
            {"client": "rtpmidid", "name": "Network", "address": "16:0"},
            {"client": "Midi Through", "name": "Midi Through Port-0", "address": "14:0"},
            {"client": "RtMidiIn Client", "name": "Tabloza Buffer  ", "address": "130:0"},
            {"client": "aseqdump", "name": "aseqdump        ", "address": "131:0"},
        ]
        ports = mu.find_usb_midi_outputs()
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0]["address"], "24:0")

    @patch("midi_utils.get_output_ports")
    @patch("midi_utils.get_input_ports")
    def test_get_buffer_ports_finds_virtual_port_on_output_side(self, mock_in, mock_out):
        import midi_utils as mu

        mock_out.return_value = [
            {"client": "RtMidiIn Client", "name": "Tabloza Buffer  ", "address": "130:0"},
        ]
        mock_in.return_value = []
        ports = mu.get_buffer_ports()
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0]["address"], "130:0")

    @patch("midi_utils.get_active_routes")
    @patch("midi_utils.find_usb_midi_outputs")
    @patch("midi_utils.find_rtpmidid_outputs")
    @patch("midi_utils.find_fluidsynth_input")
    def test_get_midi_status_lists_usb(self, mock_fs, mock_rtp, mock_usb, mock_routes):
        import midi_utils as mu

        mock_fs.return_value = {"client": "FLUID Synth", "name": "in", "address": "128:0"}
        mock_rtp.return_value = [{"client": "rtpmidid", "name": "Network", "address": "16:0"}]
        mock_usb.return_value = [
            {"client": "USB MIDI Interface", "name": "MIDI 1", "address": "24:0"},
        ]
        mock_routes.return_value = [{"from": "24:0", "to": "128:0"}]

        status = mu.get_midi_status()
        types = [s["type"] for s in status["sources"]]
        self.assertEqual(types, ["rtpmidi", "usb"])
        usb = status["sources"][1]
        self.assertEqual(usb["name"], "USB MIDI Interface")
        self.assertEqual(usb["status"], "connected")


if __name__ == "__main__":
    unittest.main()

# Tabloza MidiExpander

**[Italiano](README.md)** · **English**

Turns a Raspberry Pi into a headless MIDI expander with SoundFont synthesis, RTP-MIDI, and a smartphone-friendly web panel.

---

### What is Tabloza MidiExpander

Tabloza MidiExpander is a **standalone MIDI synthesizer** built on Raspberry Pi. The device runs **headless** (no screen, no buttons): everything is controlled from a browser (smartphone or PC) via a responsive web interface.

It receives MIDI over **network RTP-MIDI** (compatible with iOS, macOS, and Windows) and renders real-time audio using **FluidSynth** and SoundFont (`.sf2`) files, with configurable audio output (jack, USB, HDMI).

> **Physical GPIO MIDI** (DIN port on GPIO 14/15): planned feature, not yet active. See [docs/TODO.md](docs/TODO.md).

### Features

| Feature | Description |
|---------|-------------|
| **SF2 synthesis** | FluidSynth with web-managed SoundFont library |
| **Synth engine** | Buffer presets, polyphony, reverb, chorus, dynamic SF2 loading |
| **Audio output** | ALSA device selection (built-in jack, USB, HDMI) with volume in percent |
| **RTP-MIDI** | Discoverable as `tabloza-me.local` (rtpmidid + Avahi) |
| **Web panel** | Responsive bilingual UI (IT/EN), collapsible sections |
| **SF2 upload** | Drag-and-drop with progress bar (max 2 GB); manual or auto activation |
| **Adaptive networking** | Ethernet, WiFi client, hotspot, direct LAN link; UI shows relevant controls only |
| **Direct LAN link** | Pi ↔ computer cable without router: automatic DHCP at `192.168.5.1` |
| **WiFi provisioning** | `Tabloza-MidiExpander` hotspot when offline; connect to home networks |
| **Network monitor** | WiFi reconnect, hotspot fallback, automatic Ethernet management |
| **Diagnostics** | RAM, CPU, disk, temperature, event console and update check |
| **MIDI Reset** | Restart FluidSynth and MIDI routing in one click |
| **Security** | Password login (default: `tabloza`) |

### Web interface (UI)

Access: **http://tabloza-me.local** (or the IP shown in Status)

The UI is **bilingual** (IT/EN): use the **IT** / **EN** buttons at the top. Language preference is saved in the browser.

| Section | Purpose |
|---------|---------|
| **Status** | mDNS address, per-interface IP (labeled), network mode with WiFi name, active SF2, version, activity meters, sound/jack test, MIDI Reset |
| **Audio output volume** | **0–100%** slider, auto-saved |
| **Audio output** | ALSA playback device list; switch output (jack, USB, HDMI…) with synth restart |
| **Synth engine** | Buffer preset, polyphony, reverb, chorus, dynamic loading; *Stop notes* |
| **SoundFont Library** | List, load, delete, upload `.sf2` files |
| **Network** | Active mode badge; direct LAN, hotspot and WiFi client (shown based on state) |
| **Diagnostics** | System metrics (RAM, CPU, disk, temperature), update check, event console |
| **Security** | Change password (collapsible section) |

### Network modes

The panel detects connectivity automatically and adapts available controls.

| Mode (Status) | Meaning |
|---------------|---------|
| **Ethernet** | LAN cable to router only |
| **Wi‑Fi · *network name*** | WiFi client only |
| **Ethernet + Wi‑Fi · *network name*** | Cable and WiFi client active together |
| **Hotspot** | Pi broadcasts `Tabloza-MidiExpander` (e.g. first boot or offline) |
| **Direct LAN link** | Direct Pi ↔ computer cable, Pi @ `192.168.5.1` |
| **Offline** | No usable connectivity |

**IP in Status:** when multiple interfaces are active, both are shown, e.g. `192.168.178.143 (Ethernet) · 192.168.178.50 (Wi‑Fi)`.

**Ethernet with router:** the Pi tries normal DHCP first. If the cable is plugged in but no IP arrives within ~25 s (e.g. direct link to a computer), it automatically switches to **direct LAN link** (`192.168.5.1`, DHCP on the cable). You can force start/stop from the panel.

**Hotspot:** starts automatically when there is no Ethernet or configured WiFi; can be started/stopped manually when not on router LAN. With a router cable connected, hotspot remains optional (handy for phone setup).

**WiFi client:** scan networks, password, profile saved in NetworkManager. With Ethernet active you can also enable WiFi (dual-homed).

### Synth engine (FluidSynth)

**Synth engine** section (collapsible). Settings are stored in `config.json` and persist across reboots.

| Setting | Description | Synth restart |
|---------|-------------|---------------|
| **Audio buffer preset** | `Standard` (512×6), `Low latency` (256×4), `Stable` (1024×8) | Yes |
| **Polyphony** | 32–512 simultaneous voices (default 256) | No |
| **Reverb** | FluidSynth reverb effect | No |
| **Chorus** | FluidSynth chorus effect | No |
| **Dynamic SF2 loading** | Load SF2 samples on demand (less RAM, more I/O) | Yes |

- **Apply** — save and apply; restarts FluidSynth only when needed (buffer or dynamic loading).
- **Restore standard** — reset to Standard preset with polyphony 256, reverb/chorus on.
- **Stop notes** — sends all-notes-off without restarting the engine.

Tips:
- **Standard** — good default on Pi 4/5.
- **Low latency** — live performance; higher CPU load.
- **Stable** — very large SF2 files or stressed systems.

### Audio output

| Control | Description |
|---------|-------------|
| **Audio output volume** | 0–100% on the ALSA mixer (PCM/Headphone/Master of the active device) |
| **Device** | ALSA card for FluidSynth: jack `plughw:0,0`, USB `hw:N,0`, HDMI, etc. |
| **Apply output** | Change device and restart the synth |
| **Sound test** | Test note via FluidSynth (checks SF2 + routing) |
| **Jack test** | Direct beep on ALSA hardware (bypasses FluidSynth) |

USB/HDMI cards may automatically use a 48 kHz sample rate.

### Diagnostics

Collapsible **Diagnostics** section, auto-refreshed every ~2 s while open:

| Block | Content |
|-------|---------|
| **RAM** | Usage percent, used/total MB, free memory, FluidSynth RAM |
| **CPU** | Usage percent, load average, core count |
| **Disk** | Used/free space on `/var/lib/tabloza`, SF2 upload limit |
| **Temperature** | Raspberry Pi SoC (thermal zone or `vcgencmd`) |
| **Updates** | **Check for updates** button (GitHub → `sudo tabloza-update`) |
| **Event console** | Text logs (WiFi, network, SF2, synth, web…) with **Clear** button |

### Software updates

**From the panel:** **Diagnostics → Check for updates**. If available, installation runs in the background and services restart.

**From SSH:**

```bash
sudo tabloza-update              # install latest from GitHub
sudo tabloza-update --check-only # check only (exit 0=ok, 2=available)
```

Data in `/var/lib/tabloza/` (SF2, password, synth settings) is preserved.

### Requirements

- Raspberry Pi **4 or 5** (recommended) — Pi 3 limited support
- **Raspberry Pi OS Lite 64-bit**
- Terminal access (SSH or local)

### Installation

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
sudo reboot
```

### First access

1. Connect to the device network or hotspot `Tabloza-MidiExpander`
2. Open **http://tabloza-me.local** (or `http://<Pi-IP>`)
3. Password: `tabloza`

### Wireless RTP-MIDI setup

The Pi advertises an RTP-MIDI session on the network:
- **Name:** `tabloza-me`
- **UDP port:** `5004`
- **mDNS:** `tabloza-me.local`

Prerequisites on the Pi: upload a `.sf2` via the web panel and run `sudo tabloza-test`.

#### macOS / iOS

1. Mac and Pi on the **same WiFi/LAN**
2. Open **Audio MIDI Setup** → **Window → Show MIDI Studio**
3. **macOS Sequoia / Tahoe (15+):** **Window → Configure Network Driver** (no longer double-click Network)
   - **Older macOS:** double-click the **Network** globe icon
4. Create an **RTP** session (**+** under My Sessions) and enable the checkbox
5. Under **Directory** find **`tabloza-me`** → **Connect**
6. If missing: connect manually to host `tabloza-me.local` (or Pi IP) port **5004**
7. In your DAW: MIDI output to `tabloza-me`

Verify discovery from the Mac:
```bash
dns-sd -B _apple-midi._udp
# or
dns-sd -L tabloza-me _apple-midi._udp
```

#### Windows

1. Install [rtpMIDI](https://www.tobias-erichsen.de/software/rtpmidi.html)
2. (Recommended) Install [Bonjour](https://support.apple.com/kb/DL999) for `.local` discovery
3. Launch rtpMIDI → find **`tabloza-me`** → **Connect**
4. Manual connection: host = Pi IP, port = **5004**

#### No sound?

In the **web panel** (Status section):
- **MIDI in** pulses green when notes arrive from the Mac
- **Audio out** pulses when FluidSynth is actually playing
- **Sound test** sends middle C directly to the synth (bypasses RTP-MIDI)
- **Jack test** checks ALSA hardware directly (bypasses FluidSynth)
- Check active SF2, volume > 0, **Connected** badge on rtpmidid

**Quick SSH tests on the Pi:**

```bash
sudo tabloza-test
speaker-test -t wav -c 2 -l 1
pgrep -a fluidsynth
aconnect -l | grep -E 'fluidsynth|rtpmidid|Connected'
FS=$(aconnect -i | grep -i fluidsynth | head -1 | awk '{print $2}')
sudo amidi -p "$FS" -S "90 3C 64" && sleep 0.3 && sudo amidi -p "$FS" -S "80 3C 00"
sudo journalctl -u tabloza-orchestrator -f
```

| Web sound test | MIDI in (web) | Likely cause |
|----------------|---------------|--------------|
| Heard | No pulse | Mac not sending MIDI or RTP → FluidSynth routing broken → **MIDI Reset** |
| Silent | — | ALSA / jack / SF2 issue → `speaker-test`, check SF2 |
| Heard | Pulsing | Audio OK — check Mac/DAW volume and MIDI channel |

- Web panel → **MIDI Reset** after each new Mac connection
- SSH: `sudo systemctl restart tabloza-orchestrator rtpmidid`

### Useful commands (SSH)

```bash
sudo tabloza-test          # full diagnostics
sudo systemctl restart tabloza-web tabloza-orchestrator tabloza-wifi tabloza-lan rtpmidid
```

### Uninstall and clean reinstall

**If you have a previous version** and want a fresh start:

```bash
# 1. Uninstall (if command exists)
sudo tabloza-uninstall

# If tabloza-uninstall is not available yet, remove manually:
sudo systemctl stop tabloza-web tabloza-orchestrator tabloza-wifi tabloza-lan rtpmidid
sudo systemctl disable tabloza-web tabloza-orchestrator tabloza-wifi tabloza-lan rtpmidid
sudo rm -f /etc/systemd/system/tabloza-*.service /etc/systemd/system/rtpmidid.service
sudo rm -rf /opt/tabloza /etc/rtpmidid
sudo rm -f /etc/avahi/services/tabloza-web.service
sudo systemctl daemon-reload

# 2. (Optional) Delete saved SF2 and password
sudo rm -rf /var/lib/tabloza

# 3. Reinstall
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
sudo reboot

# 4. Verify
sudo tabloza-test
```

During `tabloza-uninstall` you can choose whether to delete `/var/lib/tabloza` (SF2, password).

### Persistent data

```
/var/lib/tabloza/
├── config.json      # active SF2, volume (%), fluidsynth (preset, polyphony, effects…)
├── auth.json        # password hash
├── secret.key       # Flask secret key
└── soundfonts/      # .sf2 library
```

Example `fluidsynth` section in `config.json`:

```json
{
  "active_soundfont": "piano.sf2",
  "volume": 85,
  "fluidsynth": {
    "audio_device": "plughw:0,0",
    "audio_preset": "standard",
    "polyphony": 256,
    "reverb": true,
    "chorus": true,
    "dynamic_sample_loading": false
  }
}
```

### Services

```bash
sudo systemctl status tabloza-web tabloza-orchestrator tabloza-wifi tabloza-lan rtpmidid
```

| Service | Role |
|---------|------|
| `tabloza-web` | Flask web panel |
| `tabloza-orchestrator` | FluidSynth, MIDI routing, SF2 loading |
| `tabloza-wifi` | WiFi monitor, hotspot fallback |
| `tabloza-lan` | Ethernet monitor, automatic direct LAN link |
| `rtpmidid` | Network RTP-MIDI session |

### Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### Update

```bash
sudo tabloza-update
```

Or from the web panel: **Diagnostics → Check for updates**.

Full reinstall (keeps data unless you delete `/var/lib/tabloza`):

```bash
curl -fsSL https://raw.githubusercontent.com/mccoy88f/Tabloza-MidiExpander/main/install.sh | sudo bash
```

Data in `/var/lib/tabloza/` is preserved.

---

## License

MIT

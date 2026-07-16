# Tabloza MidiExpander

**[Italiano](README.md)** · **English**

Turns a Raspberry Pi into a headless MIDI expander with SoundFont synthesis, RTP-MIDI, and a smartphone-friendly web panel.

The project originated as support for [www.tabloza.live](https://www.tabloza.live) and its karaoke app **Tabloza Sing**.

---

### What is Tabloza MidiExpander

Tabloza MidiExpander is a **standalone MIDI synthesizer** built on Raspberry Pi. The device runs **headless** (no screen, no buttons): everything is controlled from a browser (smartphone or PC) via a responsive web interface.

It receives MIDI over **network RTP-MIDI** (compatible with iOS, macOS, and Windows) and, in parallel, from a **USB‑MIDI dongle** plugged into the Pi. Audio uses **FluidSynth** and SoundFont (`.sf2`) files, with configurable output (jack, USB, HDMI).

> **Future development:** **GPIO MIDI** input (DIN port on UART GPIO 14/15 + optoisolator) — not implemented yet. See [docs/TODO.md](docs/TODO.md).

### Features

| Feature | Description |
|---------|-------------|
| **SF2 synthesis** | FluidSynth with web-managed SoundFont library; load verification; **Eject SF2** frees RAM |
| **Synth engine** | Audio buffer presets (default **Stable**), polyphony, reverb, chorus, dynamic SF2 loading |
| **MIDI settings** | Bank modes GM/GS/XG/MMA (default GS), RTP anti-jitter buffer, hardware-like **SysEx auto** |
| **MIDI gateway** | ALSA port `Tabloza Buffer`: RTP buffer (~25 ms) + SysEx interception toward FluidSynth |
| **Audio output** | ALSA device selection (built-in jack, USB, HDMI) with volume in percent |
| **RTP-MIDI** | Discoverable as `tabloza-me.local` (rtpmidid + Avahi) |
| **USB MIDI** | USB‑MIDI dongle/interface on the Pi, auto-routed in parallel with network MIDI |
| **Web panel** | Responsive bilingual UI (IT/EN), collapsible sections |
| **SF2 upload** | Drag-and-drop with progress bar (max 2 GB); manual or auto activation |
| **Adaptive networking** | Ethernet, WiFi client, hotspot, direct LAN link; UI shows relevant controls only |
| **Direct LAN link** | Pi ↔ computer cable without router: automatic DHCP at `192.168.5.1` |
| **WiFi provisioning** | `Tabloza-MidiExpander` hotspot when offline; connect to home networks |
| **Network monitor** | WiFi reconnect, hotspot fallback, automatic Ethernet management |
| **Diagnostics** | RAM, CPU, disk, temperature, event console and update check |
| **MIDI Reset / Stop notes** | Restart FluidSynth + routing; silence all notes without restart |
| **Security** | Password login (default: `tabloza`) |

### Web interface (UI)

Access: **http://tabloza-me.local** (or the IP shown in Status)

The UI is **bilingual** (IT/EN): use the **IT** / **EN** buttons at the top. Language preference is saved in the browser.

| Section | Purpose |
|---------|---------|
| **Status** | mDNS address, per-interface IP, network mode, SF2, version, **connections**, sound/jack test, **MIDI Reset**, **Stop notes** |
| **Audio output volume** | **0–100%** slider, auto-saved |
| **Audio output** | ALSA playback device list; switch output (jack, USB, HDMI…) with synth restart |
| **Synth engine** | Audio buffer preset, polyphony, reverb, chorus, dynamic loading |
| **MIDI settings** | Bank mode, RTP anti-jitter buffer, automatic SysEx; shows active runtime mode |
| **SoundFont Library** | List, load, delete, upload `.sf2`, **Eject SF2** (unload from RAM) |
| **Network** | Active mode badge; direct LAN, hotspot, WiFi client; **disable/enable Wi‑Fi** |
| **Diagnostics** | System metrics (RAM, CPU, disk, temperature), update check, **device reboot**, event console |
| **Security** | Change password (collapsible section) |

### Network modes

The panel detects connectivity automatically and adapts available controls.

| Mode (Status) | Meaning |
|---------------|---------|
| **Ethernet** | LAN cable to router only |
| **Wi‑Fi (*network name*)** | WiFi client only |
| **Ethernet + Wi‑Fi (*network name*)** | Cable and WiFi client active together |
| **Hotspot** | Pi broadcasts `Tabloza-MidiExpander` (password `tabloza1`) → `http://192.168.4.1` |
| **Direct LAN link** | Direct Pi ↔ computer cable, Pi @ `192.168.5.1` |
| **Offline** | No usable connectivity |

**IP in Status:** when multiple interfaces are active, both are shown, e.g. `192.168.178.143 (Ethernet) · 192.168.178.50 (Wi‑Fi)`.

**Ethernet with router:** the Pi tries normal DHCP first. If the cable is plugged in but no IP arrives within ~25 s (e.g. direct link to a computer), it automatically switches to **direct LAN link** (`192.168.5.1`, DHCP on the cable). You can force start/stop from the panel.

**Hotspot:** starts automatically when there is no Ethernet and no reachable Wi‑Fi; WPA2 password `tabloza1`, panel at `http://192.168.4.1`. If a saved Wi‑Fi network is in range, unplugging Ethernet joins that network (no hotspot). With a router cable connected, hotspot remains optional from the panel.

**WiFi client:** scan networks, password, profile saved in NetworkManager. With Ethernet active you can also enable WiFi (dual-homed). Use **Network → Disable Wi‑Fi** to turn off the radio (handy with Ethernet or direct LAN to avoid duplicate paths).

### Connections (MIDI + synth)

| Source | Status | Notes |
|--------|--------|-------|
| **RTP-MIDI (network)** | ✅ Active | From Mac/PC/iPad to `tabloza-me` — see RTP-MIDI section below |
| **USB‑MIDI (dongle on Pi)** | ✅ Active | Keyboard/controller via USB adapter; auto-routing + hot-plug |
| **GPIO DIN (UART)** | 🔜 Future development | Classic MIDI jack on GPIO 14/15 with optoisolator; UART script ready, ALSA bridge TBD |

Under **Status → Connections** you see active sources (rtpmidid, USB, Tabloza Sing WSS) and synth status (FluidSynth). After plugging a USB dongle, wait ~5 s or use **MIDI Reset**.

#### MIDI path (network and USB)

Sources no longer connect directly to FluidSynth: they go through the **Tabloza gateway** (ALSA port `Tabloza Buffer`), which can:

1. **RTP buffer** (optional, ~25 ms) — smooth Wi‑Fi jitter before the synth  
2. **SysEx auto** (optional) — detect GM/GS/XG/GM2 SysEx and switch bank mode at runtime  

```
Mac/iPad/USB  →  rtpmidid / USB-MIDI  →  Tabloza Buffer  →  FluidSynth
```

With RTP buffer off but SysEx auto on, the gateway stays up in **passthrough** (minimum MIDI latency, SysEx interception active).

### MIDI settings

**MIDI settings** section (collapsible). Stored in `config.json` → `midi` section.

| Setting | Description | Synth restart |
|---------|-------------|---------------|
| **Bank mode** | `GM`, `GS` (default), `XG`, `MMA/GM2` — how FluidSynth interprets bank select | Yes |
| **RTP anti-jitter buffer** | Delays network events ~25 ms (default **on**); useful on Wi‑Fi | No (gateway only) |
| **RTP timestamps (rtpmidid-ts)** | Schedules ALSA from sender RTP clock (default **on**) | Restarts rtpmidid |
| **Automatic SysEx** | Switch bank mode on GM/GS/XG/GM2 SysEx (default **on**) | No |

**When to use which bank mode:**

| Mode | Recommended for |
|------|-----------------|
| **GM** | Simple apps, pure GM MIDI files (ignores bank select) |
| **GS** | General compromise, GM/GS SoundFonts, Roland gear |
| **XG** | Yamaha SoundFonts (e.g. SD1000), XG files/arrangers |
| **MMA** | GM2 files or DAWs with explicit MSB+LSB |

With **automatic SysEx** enabled, a file or app sending e.g. *XG System On* temporarily switches to XG mode (shown as “active mode now” in the panel) without changing the saved default. GM2 SysEx is mapped to **MMA**.

Other SysEx (tuning, GS DT1 rhythm parts, etc.) are forwarded normally to FluidSynth.

### Synth engine (FluidSynth)

**Synth engine** section (collapsible). Settings are stored in `config.json` and persist across reboots.

| Setting | Description | Synth restart |
|---------|-------------|---------------|
| **Audio buffer preset** | `Standard` (512×6), `Low latency` (256×4), `Stable` (1024×8) — **default: Stable** | Yes |
| **Polyphony** | 32–512 simultaneous voices (default 256) | Yes |
| **Reverb** | FluidSynth reverb effect | No |
| **Chorus** | FluidSynth chorus effect | No |
| **Dynamic SF2 loading** | Load SF2 samples on demand (less RAM, more I/O) | Yes |

- **Apply** — save and apply; restarts FluidSynth only when needed (audio buffer or dynamic loading).
- **Restore stable** — reset to **Stable** preset (1024×8) with polyphony 256, reverb/chorus on.

Tips:
- **Stable** (default) — large SF2 (e.g. SD1000), Wi‑Fi/RTP, stressed systems; ~185 ms audio latency.
- **Standard** — good balance on Pi 4/5 (~70 ms audio latency).
- **Low latency** — live performance; higher CPU load (~40 ms audio latency).

> The **RTP MIDI buffer** (~25 ms) is separate from the audio buffer and is configured under **MIDI settings**.

### SoundFont library

In addition to selecting and uploading `.sf2` files:

- **Load** — load the selected SF2 into FluidSynth (with stack verification and adaptive timeout for large files).
- **Eject SF2** — unload all SF2 from RAM while keeping FluidSynth running (handy with 1+ GB maps).
- Before each new load, any previous SF2 is unloaded automatically.
- Filenames with **spaces** are supported (e.g. `SD1000 Sound Family Map.sf2`).

### Audio output

| Control | Description |
|---------|-------------|
| **Audio output volume** | 0–100% on the ALSA mixer (PCM/Headphone/Master of the active device) |
| **Device** | ALSA card for FluidSynth: jack `plughw:0,0`, USB `hw:N,0`, HDMI, etc. |
| **Apply output** | Change device and restart the synth |
| **Sound test** | Test note via FluidSynth (checks SF2 + routing) |
| **Jack test** | Direct beep on ALSA hardware (bypasses FluidSynth) |
| **Stop notes** | Silence all notes (in **Status**, next to MIDI Reset) |

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

The Pi advertises **one** RTP-MIDI session on the network:
- **Name:** `tabloza-me`
- **UDP port:** `5004`
- **mDNS:** `tabloza-me.local`

> **Single announcement and dual interface (Ethernet + Wi‑Fi)**  
> macOS Audio MIDI Setup shows **one** entry `tabloza-me` even when the Pi has both cable and Wi‑Fi up. mDNS does not label “Wi‑Fi” vs “Ethernet” in the name — it is for **discovery**, not for showing which path an active session uses.  
> An RTP-MIDI session uses **one IP path** (e.g. Wi‑Fi IP *or* Ethernet IP). If you connect over Wi‑Fi and then disable Wi‑Fi on the Pi, MIDI **stops** even if Ethernet is still plugged in — you must **reconnect**, ideally via **manual connect** to the correct IP (below).  
> **Status** shows per-interface IPs, e.g. `192.168.5.1 (Ethernet) · 192.168.178.50 (Wi‑Fi)`. For cable-only use: disable Wi‑Fi in the panel (**Network → Disable Wi‑Fi**) and connect manually to `192.168.5.1` port **5004**.

Prerequisites on the Pi: upload a `.sf2` via the web panel and run `sudo tabloza-test`.

#### macOS / iOS

1. Mac and Pi on the **same WiFi/LAN**
2. Open **Audio MIDI Setup** → **Window → Show MIDI Studio**
3. **macOS Sequoia / Tahoe (15+):** **Window → Configure Network Driver** (no longer double-click Network)
   - **Older macOS:** double-click the **Network** globe icon
4. Create an **RTP** session (**+** under My Sessions) and enable the checkbox
5. Under **Directory** find **`tabloza-me`** → **Connect**
6. If missing: connect manually to host = **Pi IP** (the one for the network you use — see Status) port **5004** — avoid `tabloza-me.local` if it resolves to the wrong IP with two interfaces up
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
aconnect -l | grep -E 'Tabloza|fluidsynth|rtpmidid|Connected'
FS=$(aconnect -i | grep -i fluidsynth | head -1 | awk '{print $2}')
sudo amidi -p "$FS" -S "90 3C 64" && sleep 0.3 && sudo amidi -p "$FS" -S "80 3C 00"
sudo journalctl -u tabloza-orchestrator -f
```

| Web sound test | MIDI in (web) | Likely cause |
|----------------|---------------|--------------|
| Heard | No pulse | Mac not sending MIDI or RTP → gateway/FluidSynth routing broken → **MIDI Reset** |
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
├── config.json      # active SF2, volume (%), fluidsynth, midi (banks, RTP buffer, SysEx)…
├── auth.json        # password hash
├── secret.key       # Flask secret key
└── soundfonts/      # .sf2 library
```

Example `config.json` (excerpt):

```json
{
  "active_soundfont": "piano.sf2",
  "volume": 85,
  "fluidsynth": {
    "audio_device": "plughw:0,0",
    "audio_preset": "stable",
    "period_size": 1024,
    "period_count": 8,
    "polyphony": 256,
    "reverb": true,
    "chorus": true,
    "dynamic_sample_loading": false
  },
  "midi": {
    "bank_select": "gs",
    "jitter_buffer_enabled": true,
    "jitter_buffer_ms": 25,
    "rtp_midi_timestamps_enabled": true,
    "sysex_bank_auto": true
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
| `tabloza-orchestrator` | FluidSynth, MIDI gateway (`Tabloza Buffer`), routing, SF2 loading, SysEx auto |
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

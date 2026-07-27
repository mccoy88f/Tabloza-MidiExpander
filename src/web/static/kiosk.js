/**
 * Tabloza MidiExpander — Touch Kiosk Logic (v3.1.0)
 */

document.addEventListener("DOMContentLoaded", () => {
  let currentTab = 0;
  const slider = document.getElementById("kiosk-slider");
  const tabBtns = document.querySelectorAll(".kiosk-tab-btn");

  // Touch Swipe State
  let startX = null;
  let startY = null;
  let currX = null;

  // Track adjustments so polling doesn't override sliders during drag
  let sf2GainAdjusting = false;
  let reverbAdjusting = false;
  let chorusAdjusting = false;

  // --- TAB NAVIGATION & SWIPE ---

  function goToTab(tabIndex) {
    if (tabIndex < 0 || tabIndex > 2) return;
    currentTab = tabIndex;
    slider.style.transform = `translateX(-${currentTab * 100}vw)`;

    tabBtns.forEach((btn, idx) => {
      if (idx === currentTab) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabIdx = parseInt(btn.getAttribute("data-tab"), 10);
      goToTab(tabIdx);
    });
  });

  // Touch Swipe Handlers
  document.addEventListener("touchstart", (e) => {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    currX = e.touches[0].clientX;
  }, { passive: true });

  document.addEventListener("touchmove", (e) => {
    currX = e.touches[0].clientX;
  }, { passive: true });

  document.addEventListener("touchend", (e) => {
    if (startX === null || currX === null || startY === null) return;
    const diffX = currX - startX;
    const diffY = e.changedTouches[0].clientY - startY;

    if (Math.abs(diffX) > 50 && Math.abs(diffX) > Math.abs(diffY) * 1.5) {
      if (diffX < 0 && currentTab < 2) {
        goToTab(currentTab + 1);
      } else if (diffX > 0 && currentTab > 0) {
        goToTab(currentTab - 1);
      }
    }
    startX = null;
    startY = null;
    currX = null;
  });

  // --- NETWORK MODE FORMATTING ---

  function formatNetworkMode(mode, net = {}) {
    const wifi = net.wifi_connection || "";
    switch (mode) {
      case "hotspot": return "Hotspot";
      case "client": return wifi ? `Wi-Fi (${wifi})` : "Wi-Fi";
      case "ethernet": return "Ethernet";
      case "lan_wifi": return wifi ? `Ethernet + Wi-Fi (${wifi})` : "Ethernet + Wi-Fi";
      case "lan_direct": return "Link LAN Diretto";
      case "offline": return "Offline";
      default: return "—";
    }
  }

  // --- API STATUS & POLLING ---

  async function fetchStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) throw new Error("Status error");
      const data = await res.json();
      updateUI(data);
    } catch {
      const dot = document.getElementById("status-dot-indicator");
      const label = document.getElementById("status-label-text");
      if (dot) dot.className = "status-dot startup";
      if (label) label.innerText = typeof t === "function" ? t("kioskStatusStarting") : "Avvio...";
    }
  }

  function updateUI(data) {
    const engineRunning = !!(data.synth && data.synth.engine_running);
    const midiReady = !!(data.synth && data.synth.midi_ready);
    const starting = !!(data.synth && data.synth.starting);
    const sfLoaded = !!(data.soundfont && data.soundfont.loaded);
    const sfLoading = !!(data.soundfont && data.soundfont.loading);

    // Header Status Dot: Grigio (Avvio...), Giallo (Caricamento...), Verde (Pronto)
    const dot = document.getElementById("status-dot-indicator");
    const label = document.getElementById("status-label-text");

    let sysState = "startup";
    let sysText = typeof t === "function" ? t("kioskStatusStarting") : "Avvio...";

    if (sfLoading || starting || (engineRunning && !midiReady)) {
      sysState = "loading";
      sysText = typeof t === "function" ? t("kioskStatusLoading") : "Caricamento...";
    } else if (engineRunning && midiReady) {
      sysState = "ready";
      sysText = typeof t === "function" ? t("kioskStatusReady") : "Pronto";
    }

    if (dot) dot.className = `status-dot ${sysState}`;
    if (label) label.innerText = sysText;

    // Host, IP & Network Mode
    if (data.hostname) {
      const hostEl = document.getElementById("kiosk-hostname");
      const netMdns = document.getElementById("net-mdns");
      if (hostEl) hostEl.innerText = data.hostname;
      if (netMdns) netMdns.innerText = data.hostname;
    }
    if (data.ip || data.network) {
      const ipEl = document.getElementById("kiosk-ip");
      const netIp = document.getElementById("net-ip");
      const ipStr = data.ip || (data.network ? (data.network.eth_ip || data.network.wifi_ip) : "---");
      if (ipEl) ipEl.innerText = `IP: ${ipStr}`;
      if (netIp) netIp.innerText = ipStr || "---";
    }

    const netModeLabel = document.getElementById("net-mode-label");
    if (netModeLabel) {
      netModeLabel.innerText = formatNetworkMode(data.network_mode || (data.network ? data.network.network_mode : ""), data.network);
    }

    // Version
    if (data.version) {
      const verText = document.getElementById("kiosk-version-text");
      if (verText) verText.innerText = `v${data.version}`;
    }

    // Master Volume
    if (data.volume !== undefined) {
      const sliderEl = document.getElementById("vol-slider");
      const volText = document.getElementById("vol-val-text");
      if (sliderEl && document.activeElement !== sliderEl) sliderEl.value = data.volume;
      if (volText) volText.innerText = `${data.volume}%`;
    }

    // SF2 Gain Volume
    if (data.synth_gain !== undefined && !sf2GainAdjusting) {
      const sf2GainSlider = document.getElementById("sf2-gain-slider");
      const sf2GainText = document.getElementById("sf2-gain-text");
      const gainVal = Number(data.synth_gain);
      if (sf2GainSlider && document.activeElement !== sf2GainSlider) {
        sf2GainSlider.value = Math.round(gainVal * 100);
      }
      if (sf2GainText) {
        sf2GainText.innerText = `${(Math.round(gainVal * 10) / 10).toFixed(1)}×`;
      }
    }

    // Activity LED Dots (exact match with main dashboard logic in app.js)
    const setDot = (id, state) => {
      const d = document.getElementById(id);
      if (d) d.className = `act-dot ${state || "inactive"}`;
    };

    // Synth Dot
    let synthDotState = "inactive";
    if (starting || (engineRunning && !midiReady)) {
      synthDotState = "loading";
    } else if (engineRunning && midiReady) {
      synthDotState = "ready";
    }
    setDot("dot-synth", synthDotState);

    // SF2 Dot
    let sfState = "inactive";
    if (sfLoading) {
      sfState = "loading";
    } else if (sfLoaded) {
      sfState = "ready";
    }
    setDot("dot-sf2", sfState);

    // MIDI In Dot
    const midiAct = data.activity?.midi || {};
    const midiReceiving = !!midiAct.receiving;
    let midiDotState = "inactive";
    if (midiReceiving) {
      midiDotState = "live";
    } else if (starting || (engineRunning && !midiReady)) {
      midiDotState = "loading";
    } else if (midiReady) {
      midiDotState = "ready";
    }
    setDot("dot-midi", midiDotState);

    // Audio Out Dot
    const audioAct = data.activity?.audio || {};
    const audioPlaying = !!audioAct.output_active;
    let audioDotState = "inactive";
    if (audioPlaying) {
      audioDotState = "live";
    } else if (sfLoading || starting || (engineRunning && !sfLoaded)) {
      audioDotState = "loading";
    } else if (engineRunning && sfLoaded) {
      audioDotState = "ready";
    }
    setDot("dot-audio", audioDotState);

    // Connected MIDI Connections (WSS & RTP AppleMIDI)
    const container = document.getElementById("kiosk-midi-inputs");
    if (container && data.midi) {
      const m = data.midi;
      const lines = [];
      if (m.wss_enabled) {
        lines.push(`🌐 <strong>Tabloza Sing (WSS :${m.wss_port || 8765})</strong> — ${m.wss_clients || 0} client`);
      }
      if (m.rtp_midi_enabled) {
        lines.push(`🎹 <strong>RTP AppleMIDI (5004)</strong> — ${m.rtp_midi_clients || 0} sessioni`);
      }
      if (m.inputs && m.inputs.length > 0) {
        m.inputs.forEach((inp) => lines.push(`🔌 USB: ${inp}`));
      }
      container.innerHTML = lines.length > 0
        ? lines.map((l) => `<div style="padding: 2px 0;">${l}</div>`).join("")
        : "Nessuna connessione MIDI attiva";
    }

    // Synth Effects Parameters sync
    if (data.synth_settings) {
      syncSynthEffectsUI(data.synth_settings);
    }
  }

  function syncSynthEffectsUI(settings) {
    if (!settings) return;

    if (!reverbAdjusting) {
      const revToggle = document.getElementById("kiosk-reverb-toggle");
      const revLevel = document.getElementById("kiosk-reverb-level");
      const revText = document.getElementById("reverb-val-text");
      if (revToggle) revToggle.checked = !!settings.reverb;
      if (settings.reverb_effect && settings.reverb_effect.level !== undefined) {
        const l = Number(settings.reverb_effect.level);
        if (revLevel && document.activeElement !== revLevel) revLevel.value = l;
        if (revText) revText.innerText = l.toFixed(2);
      }
    }

    if (!chorusAdjusting) {
      const choToggle = document.getElementById("kiosk-chorus-toggle");
      const choLevel = document.getElementById("kiosk-chorus-level");
      const choText = document.getElementById("chorus-val-text");
      if (choToggle) choToggle.checked = !!settings.chorus;
      if (settings.chorus_effect && settings.chorus_effect.level !== undefined) {
        const l = Number(settings.chorus_effect.level);
        if (choLevel && document.activeElement !== choLevel) choLevel.value = l;
        if (choText) choText.innerText = l.toFixed(2);
      }
    }
  }

  // --- DEVICE STATS (CPU & RAM) ---

  async function fetchDeviceStats() {
    try {
      const res = await fetch("/api/device/stats");
      if (!res.ok) return;
      const data = await res.json();

      const cpuVal = document.getElementById("stat-cpu-val");
      const cpuFill = document.getElementById("stat-cpu-fill");
      const ramVal = document.getElementById("stat-ram-val");
      const ramFill = document.getElementById("stat-ram-fill");
      const tempVal = document.getElementById("stat-temp-val");

      const cpuPct = data.percent !== undefined && data.percent !== null ? data.percent : 0;
      const ramPct = data.used_percent !== undefined && data.used_percent !== null ? data.used_percent : 0;

      if (cpuVal) cpuVal.innerText = `${cpuPct}%`;
      if (cpuFill) cpuFill.style.width = `${Math.min(100, Math.max(0, cpuPct))}%`;

      if (ramVal) ramVal.innerText = `${ramPct}%`;
      if (ramFill) ramFill.style.width = `${Math.min(100, Math.max(0, ramPct))}%`;

      if (tempVal && data.temperature_c !== undefined) {
        tempVal.innerText = data.temperature_c ? `${data.temperature_c} °C` : "-- °C";
      }
    } catch {
      /* ignore */
    }
  }

  // --- AUDIO DEVICES FETCH & SELECT ---

  async function fetchAudioDevices() {
    try {
      const res = await fetch("/api/audio/devices");
      if (!res.ok) return;
      const data = await res.json();
      renderAudioDevicesSelect(data.devices || [], data.current || "");
    } catch {
      /* ignore */
    }
  }

  function renderAudioDevicesSelect(devices, currentId) {
    const select = document.getElementById("kiosk-audio-device-select");
    if (!select) return;

    if (!devices.length) {
      select.innerHTML = '<option value="">Nessuna uscita audio rilevata</option>';
      return;
    }

    select.innerHTML = devices
      .map((dev) => {
        const isSelected = dev.id === currentId || dev.active;
        return `<option value="${dev.id}" ${isSelected ? "selected" : ""}>${dev.label || dev.id}</option>`;
      })
      .join("");
  }

  const audioSelect = document.getElementById("kiosk-audio-device-select");
  if (audioSelect) {
    audioSelect.addEventListener("change", async (e) => {
      const devId = e.target.value;
      if (!devId) return;
      try {
        await fetch("/api/audio/device", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device: devId }),
        });
        fetchStatus();
      } catch {
        /* ignore */
      }
    });
  }

  // --- SOUNDFONT LIST FETCH & SELECT WITH ACTION BUTTONS ---

  async function fetchSoundfonts() {
    try {
      const res = await fetch("/api/soundfonts");
      if (!res.ok) return;
      const data = await res.json();
      renderSf2List(data.soundfonts || [], data.active || data.loaded || "", data.default || "");
    } catch {
      /* ignore */
    }
  }

  function renderSf2List(soundfonts, activeSf2, defaultSf2) {
    const container = document.getElementById("sf2-list-container");
    if (!container) return;

    if (soundfonts.length === 0) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px;">Nessun SoundFont (.sf2) trovato</div>';
      return;
    }

    container.innerHTML = soundfonts
      .map((sf) => {
        const sfName = sf.name || sf.filename;
        const isSelected = sfName === activeSf2 || sf.active || sf.loaded;
        const isDefault = sfName === defaultSf2 || sf.default;
        return `
          <div class="sf2-item-btn ${isSelected ? "active" : ""}">
            <div style="flex: 1; min-width: 0; padding-right: 8px;">
              <div class="sf2-item-title" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${sfName}</div>
              <div class="sf2-item-meta">
                ${sf.size ? `${Math.round(sf.size / (1024 * 1024))} MB` : ""}
                ${isSelected ? ' · <span style="color: var(--accent-cyan);">● Attivo</span>' : ""}
                ${isDefault ? ' · <span style="color: var(--accent-orange);">★ Predefinito</span>' : ""}
              </div>
            </div>
            <div class="sf2-action-btns">
              <button type="button" class="sf2-btn-sm ${isSelected ? "active-load" : ""} btn-sf2-load" data-sf2="${sfName}">
                ${isSelected ? "● Attivo" : "Carica"}
              </button>
              <button type="button" class="sf2-btn-sm ${isDefault ? "is-default" : ""} btn-sf2-default" data-sf2="${sfName}" data-is-default="${isDefault}">
                ${isDefault ? "★ Default" : "Predefinito"}
              </button>
            </div>
          </div>
        `;
      })
      .join("");

    // Attach Load Button Handlers
    container.querySelectorAll(".btn-sf2-load").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const sf2Name = btn.getAttribute("data-sf2");
        if (!sf2Name) return;
        btn.innerText = "Caricamento...";
        try {
          await fetch("/api/soundfonts/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: sf2Name }),
          });
          fetchSoundfonts();
          fetchStatus();
        } catch {
          /* ignore */
        }
      });
    });

    // Attach Default Button Handlers
    container.querySelectorAll(".btn-sf2-default").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const sf2Name = btn.getAttribute("data-sf2");
        const isDefault = btn.getAttribute("data-is-default") === "true";
        if (!sf2Name) return;
        try {
          if (isDefault) {
            await fetch("/api/soundfonts/default", { method: "DELETE" });
          } else {
            await fetch("/api/soundfonts/default", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: sf2Name }),
            });
          }
          fetchSoundfonts();
          fetchStatus();
        } catch {
          /* ignore */
        }
      });
    });
  }

  // --- CONTROLS & SLIDERS ---

  // Master Volume
  const volSlider = document.getElementById("vol-slider");
  if (volSlider) {
    volSlider.addEventListener("input", (e) => {
      const volText = document.getElementById("vol-val-text");
      if (volText) volText.innerText = `${e.target.value}%`;
    });
    volSlider.addEventListener("change", async (e) => {
      const val = parseInt(e.target.value, 10);
      try {
        await fetch("/api/volume", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ volume: val }),
        });
      } catch {
        /* ignore */
      }
    });
  }

  // SoundFont Volume (SF2 Gain)
  const sf2GainSlider = document.getElementById("sf2-gain-slider");
  if (sf2GainSlider) {
    sf2GainSlider.addEventListener("pointerdown", () => { sf2GainAdjusting = true; });
    sf2GainSlider.addEventListener("pointercancel", () => { sf2GainAdjusting = false; });
    sf2GainSlider.addEventListener("input", (e) => {
      sf2GainAdjusting = true;
      const gain = parseInt(e.target.value, 10) / 100;
      const textEl = document.getElementById("sf2-gain-text");
      if (textEl) textEl.innerText = `${(Math.round(gain * 10) / 10).toFixed(1)}×`;
    });
    sf2GainSlider.addEventListener("change", async (e) => {
      const gain = parseInt(e.target.value, 10) / 100;
      try {
        await fetch("/api/synth/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ synth_gain: gain }),
        });
      } finally {
        sf2GainAdjusting = false;
      }
    });
  }

  // Reverb Level & Toggle
  const revSlider = document.getElementById("kiosk-reverb-level");
  const revToggle = document.getElementById("kiosk-reverb-toggle");
  if (revSlider) {
    revSlider.addEventListener("pointerdown", () => { reverbAdjusting = true; });
    revSlider.addEventListener("pointercancel", () => { reverbAdjusting = false; });
    revSlider.addEventListener("input", (e) => {
      reverbAdjusting = true;
      const revText = document.getElementById("reverb-val-text");
      if (revText) revText.innerText = Number(e.target.value).toFixed(2);
    });
    revSlider.addEventListener("change", async (e) => {
      const l = parseFloat(e.target.value);
      try {
        await fetch("/api/synth/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            reverb: revToggle ? revToggle.checked : true,
            reverb_effect: { level: l }
          }),
        });
      } finally {
        reverbAdjusting = false;
      }
    });
  }
  if (revToggle) {
    revToggle.addEventListener("change", async () => {
      const l = revSlider ? parseFloat(revSlider.value) : 0.5;
      try {
        await fetch("/api/synth/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            reverb: revToggle.checked,
            reverb_effect: { level: l }
          }),
        });
      } catch {
        /* ignore */
      }
    });
  }

  // Chorus Level & Toggle
  const choSlider = document.getElementById("kiosk-chorus-level");
  const choToggle = document.getElementById("kiosk-chorus-toggle");
  if (choSlider) {
    choSlider.addEventListener("pointerdown", () => { chorusAdjusting = true; });
    choSlider.addEventListener("pointercancel", () => { chorusAdjusting = false; });
    choSlider.addEventListener("input", (e) => {
      chorusAdjusting = true;
      const choText = document.getElementById("chorus-val-text");
      if (choText) choText.innerText = Number(e.target.value).toFixed(2);
    });
    choSlider.addEventListener("change", async (e) => {
      const l = parseFloat(e.target.value);
      try {
        await fetch("/api/synth/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chorus: choToggle ? choToggle.checked : true,
            chorus_effect: { level: l }
          }),
        });
      } finally {
        chorusAdjusting = false;
      }
    });
  }
  if (choToggle) {
    choToggle.addEventListener("change", async () => {
      const l = choSlider ? parseFloat(choSlider.value) : 0.6;
      try {
        await fetch("/api/synth/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chorus: choToggle.checked,
            chorus_effect: { level: l }
          }),
        });
      } catch {
        /* ignore */
      }
    });
  }

  // Reset Effects Button
  const btnResetEffects = document.getElementById("btn-kiosk-reset-effects");
  if (btnResetEffects) {
    btnResetEffects.addEventListener("click", async () => {
      if (revSlider) revSlider.value = 0.5;
      if (revToggle) revToggle.checked = true;
      if (choSlider) choSlider.value = 0.6;
      if (choToggle) choToggle.checked = true;

      const revText = document.getElementById("reverb-val-text");
      const choText = document.getElementById("chorus-val-text");
      if (revText) revText.innerText = "0.50";
      if (choText) choText.innerText = "0.60";

      try {
        await fetch("/api/synth/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            reverb: true,
            chorus: true,
            reverb_effect: { level: 0.5 },
            chorus_effect: { level: 0.6 }
          }),
        });
      } catch {
        /* ignore */
      }
    });
  }

  // PANIC Button
  const btnPanic = document.getElementById("btn-panic-stop");
  if (btnPanic) {
    btnPanic.addEventListener("click", async () => {
      const btnText = document.getElementById("panic-btn-text");
      if (btnText) btnText.innerText = "Invio in corso...";

      try {
        await fetch("/api/synth/stop-notes", { method: "POST" });
        btnPanic.classList.add("success");
        if (btnText) btnText.innerText = "NOTE SILENZIATE!";
        setTimeout(() => {
          btnPanic.classList.remove("success");
          if (btnText) btnText.innerText = "PANIC — SILENZIA TUTTO";
        }, 2500);
      } catch {
        if (btnText) btnText.innerText = "Errore invio Panic";
        setTimeout(() => {
          if (btnText) btnText.innerText = "PANIC — SILENZIA TUTTO";
        }, 2500);
      }
    });
  }

  // Sound Test Button
  const btnSoundTest = document.getElementById("btn-sound-test");
  if (btnSoundTest) {
    btnSoundTest.addEventListener("click", async () => {
      try {
        await fetch("/api/audio/test", { method: "POST" });
      } catch {
        /* ignore */
      }
    });
  }

  // MIDI Reset Button
  const btnMidiReset = document.getElementById("btn-midi-reset");
  if (btnMidiReset) {
    btnMidiReset.addEventListener("click", async () => {
      try {
        await fetch("/api/midi/reset", { method: "POST" });
      } catch {
        /* ignore */
      }
    });
  }

  // REBOOT MODAL HANDLERS
  const rebootModal = document.getElementById("reboot-modal");
  const btnOpenRebootModal = document.getElementById("btn-open-reboot-modal");
  const btnRebootCancel = document.getElementById("btn-reboot-modal-cancel");
  const btnRebootConfirm = document.getElementById("btn-reboot-modal-confirm");

  if (btnOpenRebootModal && rebootModal) {
    btnOpenRebootModal.addEventListener("click", () => {
      rebootModal.classList.remove("hidden");
    });
  }

  if (btnRebootCancel && rebootModal) {
    btnRebootCancel.addEventListener("click", () => {
      rebootModal.classList.add("hidden");
    });
  }

  if (btnRebootConfirm && rebootModal) {
    btnRebootConfirm.addEventListener("click", async () => {
      rebootModal.classList.add("hidden");
      try {
        await fetch("/api/device/reboot", { method: "POST" });
        alert("Riavvio avviato...");
      } catch {
        /* ignore */
      }
    });
  }

  // Shutdown Button
  const btnShutdown = document.getElementById("btn-shutdown");
  if (btnShutdown) {
    btnShutdown.addEventListener("click", async () => {
      if (confirm("Spegnere completamente il Raspberry Pi?")) {
        try {
          await fetch("/api/device/shutdown", { method: "POST" });
          alert("Spegnimento avviato...");
        } catch {
          /* ignore */
        }
      }
    });
  }

  // --- INITIAL STARTUP & POLLING ---
  fetchStatus();
  fetchSoundfonts();
  fetchAudioDevices();
  fetchDeviceStats();

  setInterval(fetchStatus, 3000);
  setInterval(fetchDeviceStats, 3000);
});

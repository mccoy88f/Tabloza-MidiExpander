/**
 * Tabloza MidiExpander — Touch Kiosk Logic (v3.2.0)
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

  // --- PULL TO REFRESH GESTURE HANDLER ---
  const pullIndicator = document.getElementById("kiosk-pull-indicator");
  const pullIcon = document.getElementById("pull-icon");
  const pullText = document.getElementById("pull-text");

  let pullStartY = null;
  let pullDiffY = 0;
  let isRefreshing = false;

  document.addEventListener("touchstart", (e) => {
    const isAtTop = window.scrollY === 0 || document.documentElement.scrollTop === 0;
    if (isAtTop) {
      pullStartY = e.touches[0].clientY;
      pullDiffY = 0;
    } else {
      pullStartY = null;
    }
  }, { passive: true });

  document.addEventListener("touchmove", (e) => {
    if (pullStartY === null || isRefreshing) return;
    const currentY = e.touches[0].clientY;
    pullDiffY = currentY - pullStartY;

    if (pullDiffY > 30) {
      if (pullIndicator) pullIndicator.classList.add("visible");
      if (pullDiffY > 80) {
        if (pullIcon) pullIcon.innerText = "⬆️";
        if (pullText) pullText.innerText = "Rilascia per aggiornare";
      } else {
        if (pullIcon) pullIcon.innerText = "⬇️";
        if (pullText) pullText.innerText = "Trascina in basso per aggiornare";
      }
    }
  }, { passive: true });

  document.addEventListener("touchend", async () => {
    if (pullStartY !== null && pullDiffY > 80 && !isRefreshing) {
      isRefreshing = true;
      if (pullIcon) {
        pullIcon.innerText = "↻";
        pullIcon.classList.add("spin-icon");
      }
      if (pullText) pullText.innerText = "Aggiornamento in corso...";
      if (pullIndicator) pullIndicator.classList.add("visible");

      try {
        await Promise.all([
          fetchStatus(),
          fetchSoundfonts(),
          fetchAudioDevices(),
          fetchDeviceStats()
        ]);
        if (pullText) pullText.innerText = "Aggiornato!";
      } catch {
        if (pullText) pullText.innerText = "Errore aggiornamento";
      } finally {
        setTimeout(() => {
          if (pullIndicator) pullIndicator.classList.remove("visible");
          if (pullIcon) pullIcon.classList.remove("spin-icon");
          isRefreshing = false;
        }, 800);
      }
    } else if (pullIndicator && !isRefreshing) {
      pullIndicator.classList.remove("visible");
    }
    pullStartY = null;
    pullDiffY = 0;
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

    // Active SoundFont Display Name Under Activity LEDs
    const activeSf2Display = document.getElementById("kiosk-active-sf2-display");
    if (activeSf2Display) {
      if (sfLoading) {
        activeSf2Display.innerText = "SF2 Attivo: Caricamento...";
      } else if (data.soundfont && data.soundfont.loaded) {
        activeSf2Display.innerText = `SF2 Attivo: ${data.soundfont.loaded}`;
      } else {
        activeSf2Display.innerText = "SF2 Attivo: Nessuno";
      }
    }

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

    // Activity LED Dots
    const setDot = (id, state) => {
      const d = document.getElementById(id);
      if (d) d.className = `act-dot ${state || "inactive"}`;
    };

    let synthDotState = "inactive";
    if (starting || (engineRunning && !midiReady)) {
      synthDotState = "loading";
    } else if (engineRunning && midiReady) {
      synthDotState = "ready";
    }
    setDot("dot-synth", synthDotState);

    let sfState = "inactive";
    if (sfLoading) {
      sfState = "loading";
    } else if (sfLoaded) {
      sfState = "ready";
    }
    setDot("dot-sf2", sfState);

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

    // Connected MIDI Connections
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

  // --- SOUNDFONT LIST FETCH & SELECT WITH STAR BUTTON ---

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
              </div>
            </div>
            <div class="sf2-action-btns">
              <button type="button" class="sf2-btn-sm ${isSelected ? "active-load" : ""} btn-sf2-load" data-sf2="${sfName}">
                ${isSelected ? "● Attivo" : "Carica"}
              </button>
              <button type="button" class="sf2-btn-star ${isDefault ? "is-default" : ""} btn-sf2-default" data-sf2="${sfName}" data-is-default="${isDefault}" title="${isDefault ? "Predefinito all'avvio" : "Imposta come predefinito"}">
                ${isDefault ? "★" : "☆"}
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
        btn.disabled = true;
        try {
          await fetch("/api/soundfonts/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: sf2Name }),
          });
          fetchSoundfonts();
          fetchStatus();
        } catch {
          btn.disabled = false;
        }
      });
    });

    // Attach Default Star Button Handlers
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

  // PANIC Button (Stop notes + reset controllers)
  const btnPanic = document.getElementById("btn-panic-stop");
  if (btnPanic) {
    btnPanic.addEventListener("click", async () => {
      const btnText = document.getElementById("panic-btn-text");
      if (btnText) btnText.innerText = "Invio in corso...";

      try {
        await fetch("/api/synth/stop-notes", { method: "POST" });
        btnPanic.classList.add("success");
        if (btnText) btnText.innerText = "NOTE & SILENZIATE!";
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
      btnSoundTest.innerText = "🔊 Riproduzione nota C4...";
      btnSoundTest.disabled = true;

      const audioDot = document.getElementById("dot-audio");
      const statusDot = document.getElementById("status-dot-indicator");
      if (audioDot) audioDot.className = "act-dot live";
      if (statusDot) statusDot.className = "status-dot ready";

      try {
        await fetch("/api/audio/test", { method: "POST" });
      } catch {
        /* ignore */
      } finally {
        setTimeout(() => {
          btnSoundTest.innerText = "🔊 Test Suono (Nota C4)";
          btnSoundTest.disabled = false;
          fetchStatus();
        }, 1800);
      }
    });
  }

  // Restart Software Button
  const btnRestartSoftware = document.getElementById("btn-kiosk-restart-software");
  if (btnRestartSoftware) {
    btnRestartSoftware.addEventListener("click", async () => {
      btnRestartSoftware.innerText = "Riavvio in corso...";
      btnRestartSoftware.disabled = true;
      try {
        await fetch("/api/synth/restart-software", { method: "POST" });
        setTimeout(() => {
          btnRestartSoftware.innerText = "🔄 Riavvia Software";
          btnRestartSoftware.disabled = false;
          fetchStatus();
        }, 3000);
      } catch {
        btnRestartSoftware.innerText = "Errore Riavvio";
        setTimeout(() => {
          btnRestartSoftware.innerText = "🔄 Riavvia Software";
          btnRestartSoftware.disabled = false;
        }, 3000);
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

  // --- CONNECTION WIZARD MODAL WIZARD LOGIC ---
  const connWizardModal = document.getElementById("conn-wizard-modal");
  const btnOpenConnWizard = document.getElementById("btn-open-conn-wizard");
  const btnWizardBack = document.getElementById("btn-wizard-back");
  const btnWizardClose = document.getElementById("btn-wizard-close");
  const wizardStepIndicator = document.getElementById("wizard-step-indicator");
  const wizardContentArea = document.getElementById("wizard-content-area");

  let wizardStep = 1;

  if (btnOpenConnWizard && connWizardModal) {
    btnOpenConnWizard.addEventListener("click", () => {
      connWizardModal.classList.remove("hidden");
      showWizardStep(1);
    });
  }

  if (btnWizardClose && connWizardModal) {
    btnWizardClose.addEventListener("click", () => {
      connWizardModal.classList.add("hidden");
    });
  }

  if (btnWizardBack) {
    btnWizardBack.addEventListener("click", () => {
      if (wizardStep > 1) {
        showWizardStep(wizardStep - 1);
      }
    });
  }

  function showWizardStep(step) {
    wizardStep = step;
    if (step === 1) {
      if (btnWizardBack) btnWizardBack.classList.add("hidden");
      if (wizardStepIndicator) wizardStepIndicator.innerText = "Passo 1: Seleziona tipo di rete";
      renderWizardStep1();
    }
  }

  function renderWizardStep1() {
    if (!wizardContentArea) return;
    wizardContentArea.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 10px;">
        <button type="button" class="kiosk-btn kiosk-btn-primary" id="wizard-opt-wifi" style="height: 52px; font-size: 14px; font-weight: bold; text-align: left; padding: 0 16px;">
          📶 Configura Rete Wi-Fi
        </button>
        <button type="button" class="kiosk-btn" id="wizard-opt-lan" style="height: 52px; font-size: 14px; font-weight: bold; text-align: left; padding: 0 16px;">
          🔌 Configura Ethernet / LAN
        </button>
      </div>
    `;

    document.getElementById("wizard-opt-wifi")?.addEventListener("click", () => {
      showWizardStep2Wifi();
    });

    document.getElementById("wizard-opt-lan")?.addEventListener("click", () => {
      showWizardStep2Lan();
    });
  }

  async function showWizardStep2Wifi() {
    wizardStep = 2;
    if (btnWizardBack) btnWizardBack.classList.remove("hidden");
    if (wizardStepIndicator) wizardStepIndicator.innerText = "Passo 2: Modalità o Rete Wi-Fi";
    if (!wizardContentArea) return;

    wizardContentArea.innerHTML = '<div style="color: var(--text-muted); font-size: 12px;">Caricamento reti salvate...</div>';

    let savedNetworks = [];
    try {
      const res = await fetch("/api/wifi/saved");
      if (res.ok) {
        const data = await res.json();
        savedNetworks = data.saved || [];
      }
    } catch { /* ignore */ }

    let html = '<div style="display: flex; flex-direction: column; gap: 8px;">';

    if (savedNetworks.length > 0) {
      html += '<div style="font-size: 12px; font-weight: bold; color: var(--accent-cyan);">Reti Wi-Fi Salvate:</div>';
      savedNetworks.forEach((net) => {
        const ssid = typeof net === "string" ? net : (net.ssid || net.name);
        html += `
          <button type="button" class="kiosk-btn btn-wifi-select" data-ssid="${ssid}" style="font-size: 12px; text-align: left;">
            📶 Connetti a "${ssid}"
          </button>
        `;
      });
    } else {
      html += '<div style="font-size: 12px; color: var(--text-muted);">Nessuna rete Wi-Fi salvata.</div>';
    }

    html += `
      <hr style="border: none; border-top: 1px solid var(--border-color); margin: 6px 0;">
      <button type="button" class="kiosk-btn" id="btn-wizard-start-hotspot" style="font-size: 12px; text-align: left;">
        📡 Avvia Hotspot Fallback (Tabloza-Hotspot)
      </button>
      <button type="button" class="kiosk-btn kiosk-btn-danger" id="btn-wizard-disable-wifi" style="font-size: 12px; text-align: left;">
        🚫 Disattiva Wi-Fi
      </button>
    </div>`;

    wizardContentArea.innerHTML = html;

    wizardContentArea.querySelectorAll(".btn-wifi-select").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const ssid = btn.getAttribute("data-ssid");
        if (!ssid) return;
        btn.innerText = `Connessione a ${ssid}...`;
        try {
          await fetch("/api/wifi/connect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ssid }),
          });
          alert(`Connessione inviata a ${ssid}`);
          connWizardModal.classList.add("hidden");
          fetchStatus();
        } catch {
          alert("Errore invio connessione");
        }
      });
    });

    document.getElementById("btn-wizard-start-hotspot")?.addEventListener("click", async () => {
      try {
        await fetch("/api/wifi/hotspot/start", { method: "POST" });
        alert("Hotspot avviato!");
        connWizardModal.classList.add("hidden");
        fetchStatus();
      } catch {
        alert("Errore avvio hotspot");
      }
    });

    document.getElementById("btn-wizard-disable-wifi")?.addEventListener("click", async () => {
      try {
        await fetch("/api/wifi/disable", { method: "POST" });
        alert("Wi-Fi disattivato");
        connWizardModal.classList.add("hidden");
        fetchStatus();
      } catch {
        alert("Errore disattivazione Wi-Fi");
      }
    });
  }

  function showWizardStep2Lan() {
    wizardStep = 2;
    if (btnWizardBack) btnWizardBack.classList.remove("hidden");
    if (wizardStepIndicator) wizardStepIndicator.innerText = "Passo 2: Modalità Ethernet (LAN)";
    if (!wizardContentArea) return;

    wizardContentArea.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 10px;">
        <button type="button" class="kiosk-btn kiosk-btn-primary" id="btn-lan-dhcp" style="height: 48px; font-size: 13px; font-weight: bold; text-align: left;">
          🌐 Modalità DHCP Normale (Router Casa/Studio)
        </button>
        <button type="button" class="kiosk-btn" id="btn-lan-direct" style="height: 48px; font-size: 13px; font-weight: bold; text-align: left;">
          🔌 Link LAN Diretto PC/Mac (192.168.5.1)
        </button>
      </div>
    `;

    document.getElementById("btn-lan-dhcp")?.addEventListener("click", async () => {
      try {
        await fetch("/api/network/lan-direct/stop", { method: "POST" });
        alert("Impostata modalità LAN DHCP normale");
        connWizardModal.classList.add("hidden");
        fetchStatus();
      } catch {
        alert("Errore impostazione LAN DHCP");
      }
    });

    document.getElementById("btn-lan-direct")?.addEventListener("click", async () => {
      try {
        await fetch("/api/network/lan-direct/start", { method: "POST" });
        alert("Attivato Link LAN Diretto su 192.168.5.1");
        connWizardModal.classList.add("hidden");
        fetchStatus();
      } catch {
        alert("Errore attivazione Link LAN Diretto");
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

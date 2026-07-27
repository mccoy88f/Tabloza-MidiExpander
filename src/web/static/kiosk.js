/**
 * Tabloza MidiExpander — Touch Kiosk Logic (4.3" 800x480 & Mobile)
 */

document.addEventListener("DOMContentLoaded", () => {
  let currentTab = 0;
  const slider = document.getElementById("kiosk-slider");
  const tabBtns = document.querySelectorAll(".kiosk-tab-btn");

  // Touch Swipe State
  let startX = null;
  let startY = null;
  let currX = null;

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

    // Trigger horizontal swipe if horizontal displacement > 50px and larger than vertical
    if (Math.abs(diffX) > 50 && Math.abs(diffX) > Math.abs(diffY) * 1.5) {
      if (diffX < 0 && currentTab < 2) {
        goToTab(currentTab + 1); // Swipe left -> Next tab
      } else if (diffX > 0 && currentTab > 0) {
        goToTab(currentTab - 1); // Swipe right -> Prev tab
      }
    }
    startX = null;
    startY = null;
    currX = null;
  });

  // --- API INTEGRATION & POLLING ---

  async function fetchStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) throw new Error("Status error");
      const data = await res.json();
      updateUI(data);
    } catch (err) {
      const dot = document.getElementById("status-dot-indicator");
      const label = document.getElementById("status-label-text");
      if (dot) {
        dot.className = "status-dot offline";
      }
      if (label) {
        label.innerText = "Offline";
      }
    }
  }

  function updateUI(data) {
    // Header status dot
    const dot = document.getElementById("status-dot-indicator");
    const label = document.getElementById("status-label-text");
    const isOnline = data.synth && data.synth.engine_running;

    if (dot) {
      dot.className = `status-dot ${isOnline ? "online" : "offline"}`;
    }
    if (label) {
      label.innerText = isOnline ? "FluidSynth OK" : "Inattivo";
    }

    // Host & IP
    if (data.hostname) {
      const hostEl = document.getElementById("kiosk-hostname");
      const netMdns = document.getElementById("net-mdns");
      if (hostEl) hostEl.innerText = data.hostname;
      if (netMdns) netMdns.innerText = data.hostname;
    }
    if (data.ip) {
      const ipEl = document.getElementById("kiosk-ip");
      const netIp = document.getElementById("net-ip");
      if (ipEl) ipEl.innerText = `IP: ${data.ip}`;
      if (netIp) netIp.innerText = data.ip;
    }
    if (data.network && data.network.ssid) {
      const netName = document.getElementById("net-name");
      if (netName) netName.innerText = data.network.ssid;
    }

    // Volume
    if (data.volume !== undefined) {
      const sliderEl = document.getElementById("vol-slider");
      const volText = document.getElementById("vol-val-text");
      if (sliderEl && document.activeElement !== sliderEl) {
        sliderEl.value = data.volume;
      }
      if (volText) volText.innerText = `${data.volume}%`;
    }

    // Activity Dots
    if (data.activity) {
      const setDot = (id, active) => {
        const d = document.getElementById(id);
        if (d) d.className = `act-dot ${active ? "active" : ""}`;
      };
      setDot("dot-synth", data.synth && data.synth.engine_running);
      setDot("dot-sf2", data.soundfont && data.soundfont.loaded);
      setDot("dot-midi", data.activity.midi && data.activity.midi.active);
      setDot("dot-audio", data.activity.audio && data.activity.audio.active);
    }

    // MIDI Connections
    if (data.midi && data.midi.inputs) {
      const container = document.getElementById("kiosk-midi-inputs");
      if (container) {
        if (data.midi.inputs.length === 0) {
          container.innerText = "Nessun dispositivo MIDI USB collegato";
        } else {
          container.innerHTML = data.midi.inputs
            .map((inp) => `<div style="padding: 2px 0;">🎹 <strong>${inp}</strong></div>`)
            .join("");
        }
      }
    }
  }

  // --- SOUNDFONT LIST FETCH & SELECT ---

  async function fetchSoundfonts() {
    try {
      const res = await fetch("/api/soundfonts");
      if (!res.ok) return;
      const data = await res.json();
      renderSf2List(data.soundfonts || [], data.active || "");
    } catch {
      /* ignore */
    }
  }

  function renderSf2List(soundfonts, activeSf2) {
    const container = document.getElementById("sf2-list-container");
    if (!container) return;

    if (soundfonts.length === 0) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px;">Nessun SoundFont (.sf2) trovato in /soundfonts</div>';
      return;
    }

    container.innerHTML = soundfonts
      .map((sf) => {
        const isSelected = sf.name === activeSf2 || sf.filename === activeSf2;
        return `
          <div class="sf2-item-btn ${isSelected ? "active" : ""}" data-sf2="${sf.name || sf.filename}">
            <div>
              <div class="sf2-item-title">${sf.name || sf.filename}</div>
              <div class="sf2-item-meta">${sf.size_mb ? `${sf.size_mb} MB` : ""} ${sf.is_default ? "★ Default" : ""}</div>
            </div>
            ${isSelected ? '<span style="color: var(--accent-cyan); font-weight: bold;">✓</span>' : ""}
          </div>
        `;
      })
      .join("");

    container.querySelectorAll(".sf2-item-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const sf2Name = btn.getAttribute("data-sf2");
        if (!sf2Name) return;
        try {
          await fetch("/api/soundfont/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: sf2Name }),
          });
          fetchSoundfonts();
          fetchStatus();
        } catch {
          /* ignore */
        }
      });
    });
  }

  // --- ACTION BUTTONS ---

  // Volume Slider Change
  const volSlider = document.getElementById("vol-slider");
  if (volSlider) {
    volSlider.addEventListener("input", (e) => {
      const val = e.target.value;
      const volText = document.getElementById("vol-val-text");
      if (volText) volText.innerText = `${val}%`;
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

  // PANIC Button
  const btnPanic = document.getElementById("btn-panic-stop");
  if (btnPanic) {
    btnPanic.addEventListener("click", async () => {
      const btnText = document.getElementById("panic-btn-text");
      if (btnText) btnText.innerText = "Invio in corso...";

      try {
        await fetch("/api/midi/stop-notes", { method: "POST" });
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

  // Reboot & Shutdown
  const btnReboot = document.getElementById("btn-reboot");
  if (btnReboot) {
    btnReboot.addEventListener("click", async () => {
      if (confirm("Riavviare il Raspberry Pi?")) {
        try {
          await fetch("/api/system/reboot", { method: "POST" });
          alert("Riavvio avviato...");
        } catch {
          /* ignore */
        }
      }
    });
  }

  const btnShutdown = document.getElementById("btn-shutdown");
  if (btnShutdown) {
    btnShutdown.addEventListener("click", async () => {
      if (confirm("Spegnere completamente il Raspberry Pi?")) {
        try {
          await fetch("/api/system/shutdown", { method: "POST" });
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
  setInterval(fetchStatus, 3000);
});

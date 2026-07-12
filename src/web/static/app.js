const API = "";
const STATUS_REFRESH_MS = 2000;
const STATUS_REFRESH_LOADING_MS = 800;
let lastSf2StateKey = "";
let statusFastPoll = false;
let lastAppliedSynthSettingsKey = "";
let lastAppliedMidiSettingsKey = "";

const MIDI_BANK_MODES = ["gm", "gs", "xg", "mma"];

function midiBankLabel(mode) {
  const key = `midiBank${mode.charAt(0).toUpperCase()}${mode.slice(1)}`;
  return t(key);
}

function midiSettingsKey(settings) {
  if (!settings) return "";
  return JSON.stringify({
    bank_select: settings.bank_select,
    jitter_buffer_enabled: settings.jitter_buffer_enabled,
    sysex_bank_auto: settings.sysex_bank_auto,
    runtime_bank_select: settings.runtime_bank_select,
  });
}

function synthSettingsKey(settings) {
  if (!settings) return "";
  return JSON.stringify({
    audio_preset: settings.audio_preset,
    polyphony: settings.polyphony,
    reverb: settings.reverb,
    chorus: settings.chorus,
    dynamic_sample_loading: settings.dynamic_sample_loading,
  });
}
let lastSf2Loading = false;

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    credentials: "same-origin",
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    showLogin();
    throw new Error(t("authRequired"));
  }
  if (!res.ok) throw new Error(data.error || t("errorGeneric", { code: res.status }));
  return data;
}

function showLogin() {
  stopStatusRefresh();
  document.getElementById("login-screen").classList.remove("hidden");
  document.getElementById("dashboard").classList.add("hidden");
}

function showDashboard() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("dashboard").classList.remove("hidden");
  refreshAll();
  startStatusRefresh();
}

let statusTimer = null;

function startStatusRefresh() {
  stopStatusRefresh();
  statusFastPoll = false;
  setStatusRefreshInterval(STATUS_REFRESH_MS);
}

function stopStatusRefresh() {
  if (statusTimer) clearInterval(statusTimer);
  statusTimer = null;
}

function setupLangSwitcher() {
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setLang(btn.dataset.lang);
      refreshAll();
    });
  });
}

// --- Login ---
document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const pw = document.getElementById("login-password").value;
  const errEl = document.getElementById("login-error");
  try {
    await api("/api/auth/login", { method: "POST", body: JSON.stringify({ password: pw }) });
    errEl.classList.add("hidden");
    showDashboard();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
  }
});

document.getElementById("btn-logout").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  showLogin();
});

document.getElementById("btn-choose-file").addEventListener("click", () => {
  document.getElementById("sf2-upload").click();
});

// --- Status ---
function renderMidiInputs(midi, activity) {
  const list = document.getElementById("midi-inputs-list");
  const receivingMsg = document.getElementById("midi-receiving-msg");
  const receiving = !!(activity?.midi?.receiving);

  if (receivingMsg) {
    receivingMsg.textContent = receiving ? t("midiReceiving") : "";
    receivingMsg.classList.toggle("hidden", !receiving);
  }

  list.innerHTML = "";
  const sources = (midi?.sources || []).filter((src) => src.type !== "gpio");
  if (!sources.length) {
    list.innerHTML = `<li class="midi-item muted">${t("noMidiInputs")}</li>`;
    return;
  }
  sources.forEach((src) => {
    const li = document.createElement("li");
    li.className = "midi-item";
    const name = src.type === "usb"
      ? (src.port_count > 1
        ? t("midiUsbNamedPorts", { name: src.name, count: src.port_count })
        : t("midiUsbNamed", { name: src.name }))
      : (src.port_count > 1 ? `${src.name} (${src.port_count})` : src.name);
    const badge = src.status === "connected"
      ? `<span class="badge badge-connected">${t("badgeConnected")}</span>`
      : src.status === "available"
        ? `<span class="badge badge-ok">${t("badgeActive")}</span>`
        : '<span class="badge">—</span>';
    li.innerHTML = `<span>${escapeHtml(name)}</span>${badge}`;
    list.appendChild(li);
  });
  if (midi.fluidsynth) {
    const li = document.createElement("li");
    li.className = "midi-item";
    li.innerHTML = `<span>FluidSynth (${midi.fluidsynth.address})</span><span class="badge badge-ok">${t("badgeSynth")}</span>`;
    list.appendChild(li);
  }
}

function activityDotClass(state) {
  const base = "activity-dot";
  switch (state) {
    case "error": return `${base} error`;
    case "ready": return `${base} ready`;
    case "live": return `${base} live pulse`;
    case "loading": return `${base} loading pulse`;
    default: return `${base} inactive`;
  }
}

function sf2LoadingLabel(soundfont) {
  const name = soundfont?.selected || soundfont?.name || "…";
  const pct = soundfont?.load_progress;
  if (pct != null && pct !== "") {
    return t("sf2LoadingPct", { name, pct });
  }
  return t("sf2Loading", { name });
}

function sf2LoadingBadge(pct) {
  if (pct != null && pct !== "") {
    return t("sf2LoadingBadgePct", { pct });
  }
  return t("sf2LoadingBadge");
}

function setStatusRefreshInterval(ms) {
  if (statusTimer) clearInterval(statusTimer);
  statusTimer = setInterval(refreshStatus, ms);
}

function renderSoundfontUi(soundfont, synth = null) {
  if (!soundfont) return;
  const sf2Loaded = soundfont.loaded || "";
  const sf2Loading = !!soundfont.loading;
  const sf2Error = soundfont.error;
  const starting = synth ? !!synth.starting : false;

  const dotSf2 = document.getElementById("dot-sf2");
  const valSf2 = document.getElementById("value-sf2");
  if (dotSf2) {
    let dotState = "inactive";
    if (sf2Error) {
      dotState = "error";
    } else if (sf2Loading || (starting && soundfont.selected && !sf2Loaded)) {
      dotState = "loading";
    } else if (sf2Loaded) {
      dotState = "ready";
    }
    dotSf2.className = activityDotClass(dotState);
  }
  if (valSf2) {
    if (sf2Error) {
      valSf2.textContent = sf2Error;
    } else if (sf2Loading) {
      valSf2.textContent = sf2LoadingLabel(soundfont);
    } else if (sf2Loaded) {
      valSf2.textContent = sf2Loaded;
    } else if (starting && soundfont.selected) {
      valSf2.textContent = sf2LoadingLabel(soundfont);
    } else if (soundfont.selected) {
      valSf2.textContent = t("sf2SelectedNotLoaded", { name: soundfont.selected });
    } else {
      valSf2.textContent = t("sf2NotLoaded");
    }
  }

  const statusSf2 = document.getElementById("status-sf2");
  if (statusSf2) {
    statusSf2.textContent = sf2Loaded
      || (soundfont.selected ? `${soundfont.selected} (${t("sf2Pending")})` : t("noSoundfont"));
  }
}

function renderActivity(activity, midi, synth, soundfont) {
  const midiAct = activity?.midi || {};
  const audioAct = activity?.audio || {};

  const dotSynth = document.getElementById("dot-synth");
  const valSynth = document.getElementById("value-synth");
  const dotMidi = document.getElementById("dot-midi-in");
  const valMidi = document.getElementById("value-midi-in");
  const dotAudio = document.getElementById("dot-audio-out");
  const valAudio = document.getElementById("value-audio-out");

  const engineRunning = !!(synth?.engine_running);
  const midiReady = !!(synth?.midi_ready);
  const starting = !!(synth?.starting);
  let synthDotState = "inactive";
  if (starting || (engineRunning && !midiReady)) {
    synthDotState = "loading";
  } else if (engineRunning && midiReady) {
    synthDotState = "ready";
  }
  dotSynth.className = activityDotClass(synthDotState);
  valSynth.textContent = engineRunning
    ? (midiReady ? t("synthReady") : t("synthMidiPending"))
    : starting ? t("synthStarting") : t("synthStopped");

  renderSoundfontUi(soundfont, synth);

  const midiReceiving = !!midiAct.receiving;
  let midiDotState = "inactive";
  if (midiReceiving) {
    midiDotState = "live";
  } else if (starting || (engineRunning && !midiReady)) {
    midiDotState = "loading";
  } else if (midiReady) {
    midiDotState = "ready";
  }
  dotMidi.className = activityDotClass(midiDotState);
  valMidi.textContent = midiReceiving
    ? t("midiReceiving")
    : midiReady
      ? t("midiIdle")
      : starting ? t("midiStarting") : t("midiNoRoute");

  const audioPlaying = !!audioAct.output_active;
  const sf2Loaded = soundfont?.loaded || "";
  const sf2Loading = !!soundfont?.loading;
  let audioDotState = "inactive";
  if (audioPlaying) {
    audioDotState = "live";
  } else if (sf2Loading || starting || (engineRunning && !sf2Loaded)) {
    audioDotState = "loading";
  } else if (engineRunning && sf2Loaded) {
    audioDotState = "ready";
  }
  dotAudio.className = activityDotClass(audioDotState);
  valAudio.textContent = audioPlaying
    ? t("audioPlaying")
    : engineRunning
      ? (sf2Loaded ? t("audioIdle") : t("audioNoSf2"))
      : starting ? t("audioStarting") : t("audioStopped");
}

function formatStatusIp(net, fallback = "—") {
  if (!net) return fallback;
  const eth = net.eth_ip || "";
  const wifi = net.wifi_ip || "";
  if (eth && wifi) {
    return `${t("statusIpEth", { ip: eth })} · ${t("statusIpWifi", { ip: wifi })}`;
  }
  if (eth) return eth;
  if (wifi) return wifi;
  return fallback;
}

function networkModeLabel(mode, net = {}) {
  const wifi = net.wifi_connection || "";
  switch (mode) {
    case "hotspot": return t("networkHotspot");
    case "client": return wifi ? t("networkWifiNamed", { name: wifi }) : t("networkWifi");
    case "ethernet": return t("networkEthernet");
    case "lan_wifi":
      return wifi ? t("networkLanWifiNamed", { name: wifi }) : t("networkLanWifi");
    case "lan_direct": return t("networkLanDirect");
    case "offline": return t("networkOffline");
    default: return t("networkUnknown");
  }
}

function renderNetworkSection(s) {
  const net = s.network || {};
  const mode = s.network_mode || net.network_mode || "offline";
  const badge = document.getElementById("network-status-badge");
  const blockLan = document.getElementById("block-lan-direct");
  const blockHotspot = document.getElementById("block-hotspot");
  const blockWifi = document.getElementById("block-wifi-client");
  const blockWifiPower = document.getElementById("block-wifi-power");
  const btnLanStart = document.getElementById("btn-lan-direct-start");
  const btnLanStop = document.getElementById("btn-lan-direct-stop");
  const btnHotspotStart = document.getElementById("btn-hotspot-start");
  const btnHotspotStop = document.getElementById("btn-hotspot-stop");
  const btnWifiDisable = document.getElementById("btn-wifi-disable");
  const btnWifiEnable = document.getElementById("btn-wifi-enable");
  const hintLan = document.getElementById("hint-lan-direct");
  const hintHotspot = document.getElementById("hint-hotspot");
  const hintWifi = document.getElementById("hint-wifi");
  const hintWifiPower = document.getElementById("hint-wifi-power");

  if (!badge) return;

  badge.textContent = t("networkActiveMode", { mode: networkModeLabel(mode, net) });
  badge.dataset.mode = mode;

  const lanDirect = !!(net.lan_direct_active || mode === "lan_direct");
  const hotspot = !!(net.hotspot_active || mode === "hotspot");
  const ethRouter = !!(net.eth_on_router || mode === "ethernet" || mode === "lan_wifi");
  const wifiClient = !!(net.wifi_client_active || mode === "client" || mode === "lan_wifi");
  const wifiEnabled = net.wifi_enabled !== false;
  const wlanPresent = !!net.wlan_present;

  // Link LAN diretto: nascosto se Ethernet al router; altrimenti start O stop
  if (blockLan) {
    blockLan.classList.toggle("hidden", ethRouter);
    btnLanStart?.classList.toggle("hidden", lanDirect);
    btnLanStop?.classList.toggle("hidden", !lanDirect);
    if (hintLan) {
      hintLan.textContent = lanDirect
        ? t("lanDirectActiveHint", { ip: net.lan_direct_ip || "192.168.5.1" })
        : t("lanDirectIdleHint");
    }
  }

  // Hotspot: nascosto con Ethernet router o link LAN diretto; start O stop
  if (blockHotspot) {
    const showHotspot = !ethRouter && !lanDirect;
    blockHotspot.classList.toggle("hidden", !showHotspot);
    btnHotspotStart?.classList.toggle("hidden", hotspot);
    btnHotspotStop?.classList.toggle("hidden", !hotspot);
    if (hintHotspot) {
      hintHotspot.textContent = hotspot ? t("hotspotActiveHint") : t("hotspotIdleHint");
    }
  }

  // WiFi client: nascosto se hotspot (AP occupa wlan) o radio WiFi spenta
  if (blockWifi) {
    const showWifi = wifiEnabled && !hotspot;
    blockWifi.classList.toggle("hidden", !showWifi);
    if (hintWifi) {
      if (ethRouter) {
        hintWifi.textContent = t("wifiEthHint");
      } else if (wifiClient && net.wifi_connection) {
        hintWifi.textContent = t("wifiConnectedHint", { name: net.wifi_connection });
      } else {
        hintWifi.textContent = t("wifiScanHint");
      }
    }
  }

  if (blockWifiPower) {
    blockWifiPower.classList.toggle("hidden", !wlanPresent);
    btnWifiDisable?.classList.toggle("hidden", !wifiEnabled);
    btnWifiEnable?.classList.toggle("hidden", wifiEnabled);
    if (hintWifiPower) {
      if (!wifiEnabled) {
        hintWifiPower.textContent = t("wifiDisabledHint");
      } else if (lanDirect || ethRouter) {
        hintWifiPower.textContent = lanDirect ? t("wifiDisableLanHint") : t("wifiDisableHint");
      } else {
        hintWifiPower.textContent = t("wifiDisableHint");
      }
    }
  }
}

async function refreshStatus() {
  const s = await api("/api/status");
  document.getElementById("status-hostname").textContent = s.hostname || "—";
  document.getElementById("status-ip").textContent = formatStatusIp(s.network, s.ip || "—");
  document.getElementById("status-network").textContent = networkModeLabel(s.network_mode, s.network || {});
  renderNetworkSection(s);
  renderSoundfontUi(s.soundfont, s.synth);
  if (!volumeAdjusting) {
    const pct = Math.min(100, Math.max(0, Number(s.volume) || 0));
    document.getElementById("volume-slider").value = pct;
    document.getElementById("volume-value").textContent = pct;
  }
  if (!sf2GainAdjusting) {
    const gain = Number(s.synth_gain);
    const sliderVal = Number.isFinite(gain) ? Math.round(gain * 100) : 200;
    document.getElementById("sf2-gain-slider").value = sliderVal;
    document.getElementById("sf2-gain-value").textContent = formatSf2Gain(sliderVal / 100);
  }
  renderMidiInputs(s.midi, s.activity);
  renderActivity(s.activity, s.midi, s.synth, s.soundfont);
  if (s.synth_settings) {
    const settingsKey = synthSettingsKey(s.synth_settings);
    if (settingsKey !== lastAppliedSynthSettingsKey) {
      renderSynthSettings(s.synth_settings);
      lastAppliedSynthSettingsKey = settingsKey;
    }
  }
  if (s.midi_settings) {
    const midiKey = midiSettingsKey(s.midi_settings);
    if (midiKey !== lastAppliedMidiSettingsKey) {
      renderMidiSettings(s.midi_settings);
      lastAppliedMidiSettingsKey = midiKey;
    }
  }
  if (s.version) document.getElementById("status-version").textContent = `v${s.version}`;
  const sf = s.soundfont || {};
  const sfKey = [sf.loading, sf.loaded, sf.selected, sf.error, sf.load_progress].join("|");
  if (sf.loading && !statusFastPoll) {
    statusFastPoll = true;
    setStatusRefreshInterval(STATUS_REFRESH_LOADING_MS);
  } else if (!sf.loading && statusFastPoll) {
    statusFastPoll = false;
    setStatusRefreshInterval(STATUS_REFRESH_MS);
  }
  if (sfKey !== lastSf2StateKey) {
    lastSf2StateKey = sfKey;
    refreshSoundfonts();
  }
}

async function pollAfterUpdate(maxAttempts = 40) {
  const msg = document.getElementById("update-msg");
  msg.textContent = t("updateReconnecting");
  msg.className = "msg";
  msg.classList.remove("hidden", "ok", "err");
  for (let i = 0; i < maxAttempts; i += 1) {
    await new Promise((r) => setTimeout(r, 2000));
    try {
      const res = await fetch(`${API}/api/version`, { credentials: "same-origin" });
      if (!res.ok) continue;
      const data = await res.json();
      msg.textContent = t("updateDone", { version: data.version || "?" });
      msg.classList.add("ok");
      setTimeout(() => window.location.reload(), 1500);
      return;
    } catch {
      /* servizio in riavvio */
    }
  }
  msg.textContent = t("updateReconnectManual");
  msg.classList.add("ok");
}

document.getElementById("btn-check-update")?.addEventListener("click", async () => {
  const btn = document.getElementById("btn-check-update");
  const msg = document.getElementById("update-msg");
  btn.disabled = true;
  msg.textContent = t("updateChecking");
  msg.className = "msg";
  msg.classList.remove("hidden", "ok", "err");
  try {
    const check = await api("/api/update/check");
    if (!check.update_available) {
      msg.textContent = t("updateUpToDate", { version: check.current_version });
      msg.classList.add("ok");
      return;
    }
    msg.textContent = t("updateAvailable", {
      from: check.current_version,
      to: check.remote_version,
    });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 620000);
    let res;
    try {
      res = await fetch(`${API}/api/update/apply`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timeout);
      if (err.name === "AbortError") {
        await pollAfterUpdate();
        return;
      }
      await pollAfterUpdate();
      return;
    }
    clearTimeout(timeout);
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
      showLogin();
      throw new Error(t("authRequired"));
    }
    if (!res.ok) throw new Error(data.error || t("updateFailed"));
    if (data.applied) {
      await pollAfterUpdate();
      return;
    }
    msg.textContent = t("updateUpToDate", { version: data.current_version });
    msg.classList.add("ok");
  } catch (e) {
    msg.textContent = e.message || t("updateFailed");
    msg.classList.add("err");
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("btn-device-reboot")?.addEventListener("click", async () => {
  if (!window.confirm(t("rebootConfirm"))) return;

  const btn = document.getElementById("btn-device-reboot");
  const msg = document.getElementById("device-power-msg");
  btn.disabled = true;
  msg.textContent = t("rebootWorking");
  msg.className = "msg";
  msg.classList.remove("hidden", "ok", "err");
  try {
    await api("/api/device/reboot", { method: "POST" });
    msg.textContent = t("rebootStarted");
    msg.classList.add("ok");
    stopStatusRefresh();
    setTimeout(() => pollAfterUpdate(45), 5000);
  } catch (err) {
    msg.textContent = err.message || t("rebootFailed");
    msg.classList.add("err");
    btn.disabled = false;
  }
});

document.getElementById("btn-device-shutdown")?.addEventListener("click", async () => {
  if (!window.confirm(t("shutdownConfirm"))) return;

  const btn = document.getElementById("btn-device-shutdown");
  const msg = document.getElementById("device-power-msg");
  btn.disabled = true;
  msg.textContent = t("shutdownWorking");
  msg.className = "msg";
  msg.classList.remove("hidden", "ok", "err");
  try {
    await api("/api/device/shutdown", { method: "POST" });
    msg.textContent = t("shutdownStarted");
    msg.classList.add("ok");
    stopStatusRefresh();
  } catch (err) {
    msg.textContent = err.message || t("shutdownFailed");
    msg.classList.add("err");
    btn.disabled = false;
  }
});

document.getElementById("btn-audio-test").addEventListener("click", async () => {
  const btn = document.getElementById("btn-audio-test");
  const msg = document.getElementById("audio-test-msg");
  btn.disabled = true;
  msg.textContent = t("audioTestWorking");
  msg.className = "msg";
  msg.classList.remove("hidden");
  try {
    await api("/api/audio/test", { method: "POST" });
    msg.textContent = t("audioTestDone");
    msg.className = "msg ok";
    setTimeout(refreshStatus, 400);
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("btn-jack-test").addEventListener("click", async () => {
  const btn = document.getElementById("btn-jack-test");
  const msg = document.getElementById("audio-test-msg");
  btn.disabled = true;
  msg.textContent = t("jackTestWorking");
  msg.className = "msg";
  msg.classList.remove("hidden");
  try {
    const res = await api("/api/audio/test-hardware", { method: "POST" });
    msg.textContent = res.message || t("jackTestDone");
    msg.className = "msg ok";
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("btn-midi-reset").addEventListener("click", async () => {
  const btn = document.getElementById("btn-midi-reset");
  const msg = document.getElementById("midi-reset-msg");
  if (!confirm(t("midiResetConfirm"))) return;
  btn.disabled = true;
  btn.textContent = t("midiResetInProgress");
  msg.textContent = t("midiResetWorking");
  msg.className = "msg";
  msg.classList.remove("hidden");
  try {
    await api("/api/midi/reset", { method: "POST" });
    msg.textContent = t("midiResetDone");
    msg.className = "msg ok";
    refreshStatus();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  } finally {
    btn.disabled = false;
    btn.textContent = t("midiReset");
  }
});

document.getElementById("btn-midi-stop-notes")?.addEventListener("click", async () => {
  const btn = document.getElementById("btn-midi-stop-notes");
  const msg = document.getElementById("midi-reset-msg");
  btn.disabled = true;
  try {
    await api("/api/synth/stop-notes", { method: "POST" });
    msg.textContent = t("synthStopNotesDone");
    msg.className = "msg ok";
    msg.classList.remove("hidden");
    refreshConsole();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
    msg.classList.remove("hidden");
  } finally {
    btn.disabled = false;
  }
});

// --- SoundFonts ---
async function refreshSoundfonts() {
  const data = await api("/api/soundfonts");
  const {
    soundfonts,
    loading,
    loaded,
    active,
    error,
    load_progress: loadProgress,
    default: defaultSf = "",
  } = data;
  renderSoundfontUi({
    selected: active,
    loaded,
    loading,
    error,
    load_progress: loadProgress,
  });
  lastSf2StateKey = [loading, loaded, active, error, loadProgress].join("|");
  lastSf2Loading = !!loading;

  const ejectBtn = document.getElementById("btn-sf2-eject");
  if (ejectBtn) {
    ejectBtn.classList.toggle("hidden", !(loaded || loading || active));
  }

  const list = document.getElementById("sf2-list");
  list.innerHTML = "";
  if (!soundfonts.length) {
    list.innerHTML = `<p class="muted">${t("noSoundfontsLoaded")}</p>`;
    return;
  }
  soundfonts.forEach((sf) => {
    const div = document.createElement("div");
    div.className = "sf2-item";
    const sizeMB = (sf.size / 1024 / 1024).toFixed(1);
    const statusBadge = sf.loaded
      ? `<span class="sf2-active"> ${t("sf2LoadedBadge")}</span>`
      : sf.loading
        ? `<span class="sf2-loading"> ${sf2LoadingBadge(loadProgress)}</span>`
        : sf.selected
          ? `<span class="sf2-selected"> ${t("sf2SelectedBadge")}</span>`
          : "";
    const isDefault = sf.name === defaultSf;
    const defaultBadge = isDefault
      ? `<span class="sf2-default"> ${t("sf2DefaultBadge")}</span>`
      : "";
    div.innerHTML = `
      <div>
        <span class="sf2-name">${escapeHtml(sf.name)}</span>
        <span class="muted" style="font-size:0.8rem;margin-left:0.5rem">${sizeMB} MB</span>
        ${statusBadge}${defaultBadge}
      </div>
      <div class="sf2-actions">
        ${!sf.loaded ? `<button class="btn btn-secondary" data-load="${escapeHtml(sf.name)}">${sf.loading ? (loadProgress != null ? `${loadProgress}%` : t("loading")) : t("load")}</button>` : ""}
        <button type="button" class="btn btn-secondary sf2-default-btn${isDefault ? " is-default" : ""}" data-toggle-default="${escapeHtml(sf.name)}" title="${isDefault ? t("clearDefaultSf2") : t("setDefaultSf2")}" aria-pressed="${isDefault}">${isDefault ? "★" : "☆"}</button>
        <button class="btn btn-danger" data-del="${escapeHtml(sf.name)}">${t("delete")}</button>
      </div>`;
    list.appendChild(div);
  });

  list.querySelectorAll("[data-load]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api("/api/soundfonts/select", {
        method: "POST",
        body: JSON.stringify({ name: btn.dataset.load }),
      });
      refreshAll();
    });
  });

  list.querySelectorAll("[data-toggle-default]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = btn.dataset.toggleDefault;
      const isDefault = btn.classList.contains("is-default");
      if (isDefault) {
        await api("/api/soundfonts/default", { method: "DELETE" });
      } else {
        await api("/api/soundfonts/default", {
          method: "POST",
          body: JSON.stringify({ name }),
        });
      }
      refreshAll();
    });
  });

  list.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm(t("deleteConfirm", { name: btn.dataset.del }))) return;
      await api(`/api/soundfonts/${encodeURIComponent(btn.dataset.del)}`, { method: "DELETE" });
      refreshAll();
    });
  });
}

document.getElementById("btn-sf2-eject")?.addEventListener("click", async () => {
  const loading = lastSf2Loading;
  const confirmMsg = loading ? t("ejectSf2ConfirmLoading") : t("ejectSf2Confirm");
  if (!confirm(confirmMsg)) return;
  const btn = document.getElementById("btn-sf2-eject");
  const msg = document.getElementById("sf2-eject-msg");
  btn.disabled = true;
  btn.textContent = t("ejectSf2Working");
  msg.className = "msg hidden";
  try {
    await api("/api/soundfonts/eject", { method: "POST" });
    msg.textContent = t("ejectSf2Done");
    msg.className = "msg ok";
    await refreshAll();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  } finally {
    btn.disabled = false;
    btn.textContent = t("ejectSf2");
  }
});

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

// --- Upload ---
const uploadZone = document.getElementById("upload-zone");
const fileInput = document.getElementById("sf2-upload");

uploadZone.addEventListener("dragover", (e) => { e.preventDefault(); uploadZone.classList.add("dragover"); });
uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("dragover"));
uploadZone.addEventListener("drop", (e) => {
  e.preventDefault();
  uploadZone.classList.remove("dragover");
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => { if (fileInput.files.length) uploadFile(fileInput.files[0]); });

function uploadFile(file) {
  if (!file.name.toLowerCase().endsWith(".sf2")) {
    showUploadStatus(t("sf2Only"), true);
    return;
  }
  const maxBytes = 2 * 1024 * 1024 * 1024;
  if (file.size > maxBytes) {
    showUploadStatus(t("uploadTooLarge", { max: "2 GB" }), true);
    return;
  }

  const prog = document.getElementById("upload-progress");
  const bar = document.getElementById("upload-progress-bar");
  prog.classList.remove("hidden");
  bar.style.width = "0%";
  showUploadStatus(t("uploading", { name: file.name }), false);

  const form = new FormData();
  form.append("file", file);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/soundfonts/upload");
  xhr.withCredentials = true;

  xhr.upload.addEventListener("progress", (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      bar.style.width = `${pct}%`;
      showUploadStatus(t("uploadingPct", { pct }), false);
    }
  });

  xhr.addEventListener("load", () => {
    if (xhr.status === 401) { showLogin(); return; }
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch (_) {}
    if (xhr.status >= 200 && xhr.status < 300) {
      showUploadStatus(t("uploadDone", { name: file.name }), false, true);
      refreshAll();
    } else {
      showUploadStatus(data.error || t("uploadFailed"), true);
    }
    setTimeout(() => {
      prog.classList.add("hidden");
      bar.style.width = "0%";
    }, 2000);
    fileInput.value = "";
  });

  xhr.addEventListener("error", () => {
    showUploadStatus(t("uploadNetworkError"), true);
    prog.classList.add("hidden");
    fileInput.value = "";
  });

  xhr.send(form);
}

function showUploadStatus(msg, isError, isOk) {
  const el = document.getElementById("upload-status");
  el.textContent = msg;
  el.className = "upload-status " + (isError ? "err" : isOk ? "ok" : "");
  el.classList.remove("hidden");
}

// --- Volume ---
let volumeTimer;
let volumeAdjusting = false;
const volumeSlider = document.getElementById("volume-slider");
volumeSlider.addEventListener("pointerdown", () => { volumeAdjusting = true; });
volumeSlider.addEventListener("pointerup", () => { volumeAdjusting = false; });
volumeSlider.addEventListener("pointercancel", () => { volumeAdjusting = false; });
volumeSlider.addEventListener("input", (e) => {
  document.getElementById("volume-value").textContent = e.target.value;
  clearTimeout(volumeTimer);
  volumeTimer = setTimeout(async () => {
    await api("/api/volume", { method: "POST", body: JSON.stringify({ volume: parseInt(e.target.value) }) });
    volumeAdjusting = false;
  }, 200);
});

function formatSf2Gain(gain) {
  return (Math.round(gain * 10) / 10).toFixed(1);
}

let sf2GainTimer;
let sf2GainAdjusting = false;
const sf2GainSlider = document.getElementById("sf2-gain-slider");
if (sf2GainSlider) {
  sf2GainSlider.addEventListener("pointerdown", () => { sf2GainAdjusting = true; });
  sf2GainSlider.addEventListener("pointerup", () => { sf2GainAdjusting = false; });
  sf2GainSlider.addEventListener("pointercancel", () => { sf2GainAdjusting = false; });
  sf2GainSlider.addEventListener("input", (e) => {
    const gain = parseInt(e.target.value, 10) / 100;
    document.getElementById("sf2-gain-value").textContent = formatSf2Gain(gain);
    clearTimeout(sf2GainTimer);
    sf2GainTimer = setTimeout(async () => {
      await api("/api/synth-gain", { method: "POST", body: JSON.stringify({ gain }) });
      sf2GainAdjusting = false;
    }, 200);
  });
}

// --- Audio output ---
let currentAudioDevice = "";

async function refreshAudioDevices() {
  const select = document.getElementById("audio-device-select");
  const currentEl = document.getElementById("audio-device-current");
  if (!select || !currentEl) return;
  try {
    const data = await api("/api/audio/devices");
    currentAudioDevice = data.current || "";
    currentEl.textContent = data.current_label || data.current || "—";
    select.innerHTML = "";
    if (!data.devices || !data.devices.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = t("audioDeviceEmpty");
      select.appendChild(opt);
      select.disabled = true;
      return;
    }
    select.disabled = false;
    data.devices.forEach((dev) => {
      const opt = document.createElement("option");
      opt.value = dev.id;
      opt.textContent = dev.label;
      if (dev.id === data.current) opt.selected = true;
      select.appendChild(opt);
    });
  } catch {
    currentEl.textContent = "—";
  }
}

document.getElementById("btn-audio-refresh").addEventListener("click", refreshAudioDevices);

document.getElementById("btn-audio-apply").addEventListener("click", async () => {
  const select = document.getElementById("audio-device-select");
  const msg = document.getElementById("audio-device-msg");
  const device = select.value;
  if (!device || device === currentAudioDevice) {
    msg.textContent = t("audioDeviceNoChange");
    msg.className = "msg err";
    msg.classList.remove("hidden");
    return;
  }
  if (!confirm(t("audioDeviceConfirm"))) return;
  const btn = document.getElementById("btn-audio-apply");
  btn.disabled = true;
  msg.textContent = t("audioDeviceApplying");
  msg.className = "msg";
  msg.classList.remove("hidden");
  try {
    const res = await api("/api/audio/select", {
      method: "POST",
      body: JSON.stringify({ device }),
    });
    currentAudioDevice = res.device;
    document.getElementById("audio-device-current").textContent = res.label || res.device;
    msg.textContent = t("audioDeviceApplied", { name: res.label || res.device });
    msg.className = "msg ok";
    refreshStatus();
    refreshSoundfonts();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  } finally {
    btn.disabled = false;
  }
});

// --- Diagnostica ---
let diagnosticsTimer = null;

function setMetricBar(barEl, pct) {
  if (!barEl) return;
  const value = Math.min(100, Math.max(0, pct || 0));
  barEl.style.width = `${value}%`;
  barEl.className = "metric-bar-fill" + (
    value >= 90 ? " critical" : value >= 75 ? " warn" : ""
  );
}

function renderDeviceStats(stats) {
  if (!stats) return;

  const ramPct = stats.used_percent || 0;
  const ramValue = document.getElementById("device-ram-value");
  const ramDetail = document.getElementById("device-ram-detail");
  if (ramValue) {
    ramValue.textContent = t("memoryUsed", {
      used: stats.used_mb,
      total: stats.total_mb,
      pct: ramPct,
    });
  }
  setMetricBar(document.getElementById("device-ram-bar"), ramPct);
  if (ramDetail) {
    const parts = [t("memoryAvailable", { mb: stats.available_mb })];
    if (stats.fluidsynth_mb != null) {
      parts.push(t("memoryFluidSynth", { mb: stats.fluidsynth_mb }));
    }
    ramDetail.textContent = parts.join(" · ");
  }

  const cpuPct = stats.percent;
  const cpuValue = document.getElementById("device-cpu-value");
  const cpuDetail = document.getElementById("device-cpu-detail");
  if (cpuValue) {
    cpuValue.textContent = cpuPct != null ? `${cpuPct}%` : t("deviceUnavailable");
  }
  setMetricBar(document.getElementById("device-cpu-bar"), cpuPct ?? 0);
  if (cpuDetail) {
    cpuDetail.textContent = stats.load_1m != null
      ? t("deviceCpuDetail", { load: stats.load_1m, cores: stats.cores || 1 })
      : "";
  }

  const diskPct = stats.disk_used_percent ?? 0;
  const diskValue = document.getElementById("device-disk-value");
  const diskDetail = document.getElementById("device-disk-detail");
  if (diskValue && stats.disk_total_mb != null) {
    diskValue.textContent = t("memoryUsed", {
      used: stats.disk_used_mb,
      total: stats.disk_total_mb,
      pct: diskPct,
    });
  }
  setMetricBar(document.getElementById("device-disk-bar"), diskPct);
  if (diskDetail && stats.disk_free_mb != null) {
    diskDetail.textContent = t("deviceDiskDetail", {
      free: stats.disk_free_mb,
      max: stats.sf2_max_upload_mb,
    });
  }

  const tempValue = document.getElementById("device-temp-value");
  if (tempValue) {
    tempValue.textContent = stats.temperature_c != null
      ? `${stats.temperature_c} °C`
      : t("deviceTempUnavailable");
    tempValue.className = "device-metric-value" + (
      stats.temperature_c >= 80 ? " temp-critical"
        : stats.temperature_c >= 70 ? " temp-warn" : ""
    );
  }
}

async function refreshDeviceStats() {
  try {
    const stats = await api("/api/device/stats");
    renderDeviceStats(stats);
  } catch {
    /* ignore */
  }
}

async function refreshDiagnostics() {
  await Promise.all([refreshDeviceStats(), refreshConsole()]);
}

function setDiagnosticsPolling(enabled) {
  clearInterval(diagnosticsTimer);
  if (enabled) {
    refreshDiagnostics();
    diagnosticsTimer = setInterval(refreshDiagnostics, 2000);
  }
}

const diagnosticsSection = document.getElementById("diagnostics-section");
if (diagnosticsSection) {
  diagnosticsSection.addEventListener("toggle", () => {
    setDiagnosticsPolling(diagnosticsSection.open);
  });
}

async function refreshConsole() {
  const out = document.getElementById("console-output");
  if (!out) return;
  try {
    const { lines } = await api("/api/console");
    out.textContent = lines?.length ? lines.join("\n") : t("consoleEmpty");
    out.scrollTop = out.scrollHeight;
  } catch {
    out.textContent = t("consoleEmpty");
  }
}

document.getElementById("btn-console-clear")?.addEventListener("click", async () => {
  await api("/api/console/clear", { method: "POST" });
  refreshConsole();
});

// --- Rete ---
document.getElementById("btn-lan-direct-start")?.addEventListener("click", async () => {
  const msg = document.getElementById("lan-direct-msg");
  msg.textContent = t("startLanDirect");
  msg.className = "msg";
  msg.classList.remove("hidden", "ok", "err");
  try {
    await api("/api/network/lan-direct/start", { method: "POST" });
    msg.textContent = t("lanDirectStarted");
    msg.classList.add("ok");
    refreshStatus();
    refreshConsole();
  } catch (err) {
    msg.textContent = err.message;
    msg.classList.add("err");
    refreshConsole();
  }
});

document.getElementById("btn-lan-direct-stop")?.addEventListener("click", async () => {
  const msg = document.getElementById("lan-direct-msg");
  msg.textContent = t("stopLanDirect");
  msg.className = "msg";
  msg.classList.remove("hidden", "ok", "err");
  try {
    await api("/api/network/lan-direct/stop", { method: "POST" });
    msg.textContent = t("lanDirectStopped");
    msg.classList.add("ok");
    refreshStatus();
    refreshConsole();
  } catch (err) {
    msg.textContent = err.message;
    msg.classList.add("err");
    refreshConsole();
  }
});

document.getElementById("btn-hotspot-start")?.addEventListener("click", async () => {
  const msg = document.getElementById("wifi-msg");
  msg.textContent = t("startHotspot");
  msg.className = "msg";
  msg.classList.remove("hidden", "ok", "err");
  try {
    await api("/api/wifi/hotspot/start", { method: "POST" });
    msg.textContent = t("hotspotStarted");
    msg.classList.add("ok");
    refreshStatus();
    refreshConsole();
  } catch (err) {
    msg.textContent = err.message;
    msg.classList.add("err");
    refreshConsole();
  }
});

document.getElementById("btn-hotspot-stop")?.addEventListener("click", async () => {
  const msg = document.getElementById("wifi-msg");
  msg.textContent = t("stopHotspot");
  msg.className = "msg";
  msg.classList.remove("hidden", "ok", "err");
  try {
    await api("/api/wifi/hotspot/stop", { method: "POST" });
    msg.textContent = t("hotspotStopped");
    msg.classList.add("ok");
    refreshStatus();
    refreshConsole();
  } catch (err) {
    msg.textContent = err.message;
    msg.classList.add("err");
    refreshConsole();
  }
});

document.getElementById("btn-wifi-disable")?.addEventListener("click", async () => {
  const net = (await api("/api/status").catch(() => ({}))).network || {};
  const hasEth = !!(net.ethernet_connected || net.eth_ip);
  if (!hasEth && !window.confirm(t("wifiDisableConfirm"))) return;

  const msg = document.getElementById("wifi-msg");
  msg.textContent = t("wifiDisabling");
  msg.className = "msg";
  msg.classList.remove("hidden", "ok", "err");
  try {
    await api("/api/wifi/disable", { method: "POST" });
    msg.textContent = t("wifiDisabled");
    msg.classList.add("ok");
    refreshStatus();
    refreshConsole();
  } catch (err) {
    msg.textContent = err.message;
    msg.classList.add("err");
    refreshConsole();
  }
});

document.getElementById("btn-wifi-enable")?.addEventListener("click", async () => {
  const msg = document.getElementById("wifi-msg");
  msg.textContent = t("wifiEnabling");
  msg.className = "msg";
  msg.classList.remove("hidden", "ok", "err");
  try {
    await api("/api/wifi/enable", { method: "POST" });
    msg.textContent = t("wifiEnabled");
    msg.classList.add("ok");
    refreshStatus();
    refreshConsole();
  } catch (err) {
    msg.textContent = err.message;
    msg.classList.add("err");
    refreshConsole();
  }
});

document.getElementById("btn-wifi-scan").addEventListener("click", async () => {
  const msg = document.getElementById("wifi-msg");
  msg.textContent = t("scanningWifi");
  msg.className = "msg";
  msg.classList.remove("hidden");
  try {
    const { networks } = await api("/api/wifi/scan");
    msg.classList.add("hidden");
    refreshConsole();
    const list = document.getElementById("wifi-list");
    list.innerHTML = "";
    if (!networks.length) {
      list.innerHTML = `<p class="muted">${t("noNetworks")}</p>`;
      msg.textContent = t("noNetworks");
      msg.className = "msg";
      msg.classList.remove("hidden");
      return;
    }
    networks.forEach((n) => {
      const div = document.createElement("div");
      div.className = "wifi-item";
      div.innerHTML = `<span>${escapeHtml(n.ssid)}</span><span class="wifi-signal">${n.signal}% ${n.security ? "🔒" : ""}</span>`;
      div.addEventListener("click", () => showWifiForm(n.ssid, n.security || ""));
      list.appendChild(div);
    });
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
    refreshConsole();
  }
});

function showWifiForm(ssid, security = "") {
  const secured = !!(security && security !== "--");
  const list = document.getElementById("wifi-list");
  const form = document.createElement("div");
  form.className = "wifi-form";
  form.innerHTML = `
    <p>${t("connectTo")} <strong>${escapeHtml(ssid)}</strong>${secured ? " 🔒" : ""}</p>
    <input type="password" id="wifi-password" placeholder="${t("wifiPassword")}" autocomplete="off">
    <p class="muted wifi-hint">${secured ? t("wifiSecuredHint") : t("wifiOpenHint")}</p>
    <button class="btn btn-primary" id="wifi-connect-btn">${t("connect")}</button>`;
  list.prepend(form);
  document.getElementById("wifi-connect-btn").addEventListener("click", async () => {
    const pw = document.getElementById("wifi-password").value;
    if (secured && !pw) {
      const msg = document.getElementById("wifi-msg");
      msg.textContent = t("wifiPasswordRequired");
      msg.className = "msg err";
      msg.classList.remove("hidden");
      return;
    }
    const msg = document.getElementById("wifi-msg");
    msg.textContent = t("connecting");
    msg.className = "msg";
    msg.classList.remove("hidden");
    try {
      await api("/api/wifi/connect", {
        method: "POST",
        body: JSON.stringify({ ssid, password: pw, security }),
      });
      msg.textContent = t("connectedWifi", { ssid });
      msg.className = "msg ok";
      refreshStatus();
      refreshConsole();
    } catch (err) {
      msg.textContent = err.message;
      msg.className = "msg err";
      refreshConsole();
    }
  });
}

// --- Synth engine ---
const PRESET_I18N = {
  standard: "presetStandard",
  low_latency: "presetLowLatency",
  stable: "presetStable",
};

function presetLabel(id) {
  return t(PRESET_I18N[id] || id);
}

function updateSynthPresetHint(presetId, settings) {
  const hint = document.getElementById("synth-preset-hint");
  if (!hint) return;
  const preset = (settings?.presets || []).find((p) => p.id === presetId);
  const size = preset?.period_size ?? settings?.period_size ?? "—";
  const count = preset?.period_count ?? settings?.period_count ?? "—";
  hint.textContent = t("synthPresetHint", { size, count });
}

function renderSynthSettings(settings) {
  if (!settings) return;
  const presetSelect = document.getElementById("synth-preset");
  if (!presetSelect) return;

  presetSelect.innerHTML = "";
  (settings.presets || []).forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = presetLabel(p.id);
    if (p.id === settings.audio_preset) opt.selected = true;
    presetSelect.appendChild(opt);
  });

  document.getElementById("synth-polyphony").value = settings.polyphony;
  document.getElementById("synth-polyphony-value").textContent = settings.polyphony;
  document.getElementById("synth-reverb").checked = !!settings.reverb;
  document.getElementById("synth-chorus").checked = !!settings.chorus;
  document.getElementById("synth-dynamic").checked = !!settings.dynamic_sample_loading;
  updateSynthPresetHint(settings.audio_preset, settings);
}

async function refreshSynthSettings() {
  try {
    const settings = await api("/api/synth/settings");
    renderSynthSettings(settings);
  } catch {
    /* ignore */
  }
}

function collectSynthSettingsPayload() {
  return {
    audio_preset: document.getElementById("synth-preset").value,
    polyphony: parseInt(document.getElementById("synth-polyphony").value, 10),
    reverb: document.getElementById("synth-reverb").checked,
    chorus: document.getElementById("synth-chorus").checked,
    dynamic_sample_loading: document.getElementById("synth-dynamic").checked,
  };
}

document.getElementById("synth-polyphony")?.addEventListener("input", (e) => {
  document.getElementById("synth-polyphony-value").textContent = e.target.value;
});

document.getElementById("synth-preset")?.addEventListener("change", async (e) => {
  try {
    const settings = await api("/api/synth/settings");
    updateSynthPresetHint(e.target.value, settings);
  } catch {
    updateSynthPresetHint(e.target.value, null);
  }
});

document.getElementById("btn-synth-apply")?.addEventListener("click", async () => {
  const msg = document.getElementById("synth-msg");
  const btn = document.getElementById("btn-synth-apply");
  btn.disabled = true;
  msg.textContent = t("synthApplying");
  msg.className = "msg";
  msg.classList.remove("hidden");
  try {
    const res = await api("/api/synth/settings", {
      method: "POST",
      body: JSON.stringify(collectSynthSettingsPayload()),
    });
    renderSynthSettings(res.settings);
    lastAppliedSynthSettingsKey = synthSettingsKey(res.settings);
    msg.textContent = res.restarted ? t("synthAppliedRestart") : t("synthApplied");
    msg.className = "msg ok";
    refreshStatus();
    refreshConsole();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("btn-synth-standard")?.addEventListener("click", async () => {
  document.getElementById("synth-preset").value = "stable";
  document.getElementById("synth-polyphony").value = 256;
  document.getElementById("synth-polyphony-value").textContent = "256";
  document.getElementById("synth-reverb").checked = true;
  document.getElementById("synth-chorus").checked = true;
  document.getElementById("synth-dynamic").checked = false;
  updateSynthPresetHint("stable", { presets: [{ id: "stable", period_size: 1024, period_count: 8 }] });
  document.getElementById("btn-synth-apply").click();
});

function updateMidiBankHint(mode) {
  const hint = document.getElementById("midi-bank-hint");
  if (!hint) return;
  const key = `midiBank${mode.charAt(0).toUpperCase()}${mode.slice(1)}Hint`;
  hint.textContent = t(key);
}

function renderMidiSettings(settings) {
  if (!settings) return;
  const select = document.getElementById("midi-bank-select");
  if (!select) return;

  const current = settings.bank_select || "gs";
  select.innerHTML = "";
  (settings.bank_select_modes || MIDI_BANK_MODES).forEach((mode) => {
    const opt = document.createElement("option");
    opt.value = mode;
    opt.textContent = midiBankLabel(mode);
    if (mode === current) opt.selected = true;
    select.appendChild(opt);
  });

  document.getElementById("midi-jitter-enabled").checked = !!settings.jitter_buffer_enabled;
  document.getElementById("midi-sysex-auto").checked = !!settings.sysex_bank_auto;
  updateMidiBankHint(current);
  const runtime = document.getElementById("midi-runtime-bank");
  if (runtime && settings.runtime_bank_select) {
    runtime.textContent = t("midiRuntimeBank", { mode: settings.runtime_bank_select.toUpperCase() });
    runtime.classList.remove("hidden");
  }
}

async function refreshMidiSettings() {
  try {
    const settings = await api("/api/midi/settings");
    renderMidiSettings(settings);
    lastAppliedMidiSettingsKey = midiSettingsKey(settings);
  } catch {
    /* ignore */
  }
}

function collectMidiSettingsPayload() {
  return {
    bank_select: document.getElementById("midi-bank-select").value,
    jitter_buffer_enabled: document.getElementById("midi-jitter-enabled").checked,
    sysex_bank_auto: document.getElementById("midi-sysex-auto").checked,
  };
}

document.getElementById("midi-bank-select")?.addEventListener("change", (e) => {
  updateMidiBankHint(e.target.value);
});

document.getElementById("btn-midi-apply")?.addEventListener("click", async () => {
  const msg = document.getElementById("midi-msg");
  const btn = document.getElementById("btn-midi-apply");
  btn.disabled = true;
  msg.textContent = t("midiApplying");
  msg.className = "msg";
  msg.classList.remove("hidden");
  try {
    const res = await api("/api/midi/settings", {
      method: "POST",
      body: JSON.stringify(collectMidiSettingsPayload()),
    });
    renderMidiSettings(res.settings);
    lastAppliedMidiSettingsKey = midiSettingsKey(res.settings);
    msg.textContent = res.restarted ? t("midiAppliedRestart") : t("midiApplied");
    msg.className = "msg ok";
    refreshStatus();
    refreshConsole();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  } finally {
    btn.disabled = false;
  }
});

// --- Password ---
document.getElementById("change-password-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("password-msg");
  try {
    await api("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: document.getElementById("current-password").value,
        new_password: document.getElementById("new-password").value,
      }),
    });
    msg.textContent = t("passwordUpdated");
    msg.className = "msg ok";
    e.target.reset();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  }
  msg.classList.remove("hidden");
});

function refreshAll() {
  const onDashboard = !document.getElementById("dashboard").classList.contains("hidden");
  if (onDashboard) {
    void refreshStatus().then(() => refreshSoundfonts());
    refreshAudioDevices();
    refreshSynthSettings();
    refreshMidiSettings();
  }
}

document.addEventListener("tabloza:lang", () => {
  const sel = document.getElementById("midi-bank-select");
  if (sel) {
    [...sel.options].forEach((opt) => {
      opt.textContent = midiBankLabel(opt.value);
    });
    updateMidiBankHint(sel.value);
  }
  refreshAll();
});

// --- Init ---
async function loadFooter() {
  try {
    const v = await fetch("/api/version").then((r) => r.json());
    document.getElementById("footer-version").textContent = `v${v.version || "?"}`;
    const gh = document.getElementById("footer-github");
    if (gh && v.github) gh.href = v.github;
  } catch {
    document.getElementById("footer-version").textContent = "v?";
  }
}

setupLangSwitcher();
document.documentElement.lang = getLang();
applyI18n();
loadFooter();

(async () => {
  try {
    const { authenticated } = await api("/api/auth/check");
    authenticated ? showDashboard() : showLogin();
  } catch {
    showLogin();
  }
})();

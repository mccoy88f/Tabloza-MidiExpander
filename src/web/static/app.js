const API = "";
const STATUS_REFRESH_MS = 10000;

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    credentials: "same-origin",
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    showLogin();
    throw new Error("Non autenticato");
  }
  if (!res.ok) throw new Error(data.error || `Errore ${res.status}`);
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
  statusTimer = setInterval(refreshStatus, STATUS_REFRESH_MS);
}

function stopStatusRefresh() {
  if (statusTimer) clearInterval(statusTimer);
  statusTimer = null;
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

// --- Status ---
function renderMidiInputs(midi) {
  const list = document.getElementById("midi-inputs-list");
  list.innerHTML = "";
  if (!midi || !midi.sources || !midi.sources.length) {
    list.innerHTML = '<li class="midi-item muted">Nessun ingresso rilevato</li>';
    return;
  }
  midi.sources.forEach((src) => {
    const li = document.createElement("li");
    li.className = "midi-item";
    const badge = src.status === "planned"
      ? '<span class="badge badge-planned">In arrivo</span>'
      : src.status === "available"
        ? '<span class="badge badge-ok">Attivo</span>'
        : '<span class="badge">—</span>';
    li.innerHTML = `<span>${src.name}</span>${badge}`;
    list.appendChild(li);
  });
  if (midi.fluidsynth) {
    const li = document.createElement("li");
    li.className = "midi-item";
    li.innerHTML = `<span>FluidSynth (${midi.fluidsynth.address})</span><span class="badge badge-ok">Synth</span>`;
    list.appendChild(li);
  }
}

async function refreshStatus() {
  const s = await api("/api/status");
  document.getElementById("status-hostname").textContent = s.hostname || "—";
  document.getElementById("status-ip").textContent = s.ip;
  document.getElementById("status-network").textContent =
    s.network_mode === "hotspot" ? "Hotspot" : s.network_mode === "client" ? "WiFi" : "—";
  document.getElementById("status-sf2").textContent = s.active_soundfont || "Nessuno";
  document.getElementById("volume-slider").value = s.volume;
  document.getElementById("volume-value").textContent = s.volume;
  renderMidiInputs(s.midi);
}

document.getElementById("btn-midi-reset").addEventListener("click", async () => {
  const btn = document.getElementById("btn-midi-reset");
  const msg = document.getElementById("midi-reset-msg");
  if (!confirm("Riavviare FluidSynth e ricaricare tutto il routing MIDI?")) return;
  btn.disabled = true;
  btn.textContent = "Reset in corso…";
  msg.textContent = "Riavvio rtpmidid e FluidSynth…";
  msg.className = "msg";
  msg.classList.remove("hidden");
  try {
    const data = await api("/api/midi/reset", { method: "POST" });
    msg.textContent = data.message || "Reset completato";
    msg.className = "msg ok";
    refreshStatus();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  } finally {
    btn.disabled = false;
    btn.textContent = "MIDI Reset";
  }
});

// --- SoundFonts ---
async function refreshSoundfonts() {
  const { soundfonts } = await api("/api/soundfonts");
  const list = document.getElementById("sf2-list");
  list.innerHTML = "";
  if (!soundfonts.length) {
    list.innerHTML = '<p class="muted">Nessun SoundFont caricato</p>';
    return;
  }
  soundfonts.forEach((sf) => {
    const div = document.createElement("div");
    div.className = "sf2-item";
    const sizeMB = (sf.size / 1024 / 1024).toFixed(1);
    div.innerHTML = `
      <div>
        <span class="sf2-name">${escapeHtml(sf.name)}</span>
        <span class="muted" style="font-size:0.8rem;margin-left:0.5rem">${sizeMB} MB</span>
        ${sf.active ? '<span class="sf2-active"> ● attivo</span>' : ""}
      </div>
      <div class="sf2-actions">
        ${!sf.active ? `<button class="btn btn-secondary" data-load="${escapeHtml(sf.name)}">Carica</button>` : ""}
        <button class="btn btn-danger" data-del="${escapeHtml(sf.name)}">Elimina</button>
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

  list.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm(`Eliminare ${btn.dataset.del}?`)) return;
      await api(`/api/soundfonts/${encodeURIComponent(btn.dataset.del)}`, { method: "DELETE" });
      refreshAll();
    });
  });
}

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
    showUploadStatus("Solo file .sf2", true);
    return;
  }

  const prog = document.getElementById("upload-progress");
  const bar = document.getElementById("upload-progress-bar");
  prog.classList.remove("hidden");
  bar.style.width = "0%";
  showUploadStatus(`Caricamento ${file.name}...`, false);

  const form = new FormData();
  form.append("file", file);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/soundfonts/upload");
  xhr.withCredentials = true;

  xhr.upload.addEventListener("progress", (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      bar.style.width = `${pct}%`;
      showUploadStatus(`Caricamento ${pct}%`, false);
    }
  });

  xhr.addEventListener("load", () => {
    if (xhr.status === 401) { showLogin(); return; }
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch (_) {}
    if (xhr.status >= 200 && xhr.status < 300) {
      showUploadStatus(`${file.name} caricato e attivato`, false, true);
      refreshAll();
    } else {
      showUploadStatus(data.error || "Upload fallito", true);
    }
    setTimeout(() => {
      prog.classList.add("hidden");
      bar.style.width = "0%";
    }, 2000);
    fileInput.value = "";
  });

  xhr.addEventListener("error", () => {
    showUploadStatus("Errore di rete durante l'upload", true);
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
document.getElementById("volume-slider").addEventListener("input", (e) => {
  document.getElementById("volume-value").textContent = e.target.value;
  clearTimeout(volumeTimer);
  volumeTimer = setTimeout(async () => {
    await api("/api/volume", { method: "POST", body: JSON.stringify({ volume: parseInt(e.target.value) }) });
  }, 200);
});

// --- WiFi ---
document.getElementById("btn-wifi-scan").addEventListener("click", async () => {
  const msg = document.getElementById("wifi-msg");
  msg.textContent = "Scansione in corso...";
  msg.className = "msg";
  msg.classList.remove("hidden");
  try {
    const { networks } = await api("/api/wifi/scan");
    msg.classList.add("hidden");
    const list = document.getElementById("wifi-list");
    list.innerHTML = "";
    if (!networks.length) {
      list.innerHTML = '<p class="muted">Nessuna rete trovata</p>';
      return;
    }
    networks.forEach((n) => {
      const div = document.createElement("div");
      div.className = "wifi-item";
      div.innerHTML = `<span>${escapeHtml(n.ssid)}</span><span class="wifi-signal">${n.signal}% ${n.security ? "🔒" : ""}</span>`;
      div.addEventListener("click", () => showWifiForm(n.ssid));
      list.appendChild(div);
    });
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  }
});

function showWifiForm(ssid) {
  const list = document.getElementById("wifi-list");
  const form = document.createElement("div");
  form.className = "wifi-form";
  form.innerHTML = `
    <p>Connetti a <strong>${escapeHtml(ssid)}</strong></p>
    <input type="password" id="wifi-password" placeholder="Password WiFi">
    <button class="btn btn-primary" id="wifi-connect-btn">Connetti</button>`;
  list.prepend(form);
  document.getElementById("wifi-connect-btn").addEventListener("click", async () => {
    const pw = document.getElementById("wifi-password").value;
    const msg = document.getElementById("wifi-msg");
    msg.textContent = "Connessione in corso...";
    msg.className = "msg";
    msg.classList.remove("hidden");
    try {
      await api("/api/wifi/connect", { method: "POST", body: JSON.stringify({ ssid, password: pw }) });
      msg.textContent = `Connesso a ${ssid}. Al prossimo boot il dispositivo userà questa rete.`;
      msg.className = "msg ok";
      refreshStatus();
    } catch (err) {
      msg.textContent = err.message;
      msg.className = "msg err";
    }
  });
}

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
    msg.textContent = "Password aggiornata";
    msg.className = "msg ok";
    e.target.reset();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  }
  msg.classList.remove("hidden");
});

function refreshAll() {
  refreshStatus();
  refreshSoundfonts();
}

// --- Init ---
(async () => {
  try {
    const { authenticated } = await api("/api/auth/check");
    authenticated ? showDashboard() : showLogin();
  } catch {
    showLogin();
  }
})();

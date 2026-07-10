const API = "";

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
  document.getElementById("login-screen").classList.remove("hidden");
  document.getElementById("dashboard").classList.add("hidden");
}

function showDashboard() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("dashboard").classList.remove("hidden");
  refreshAll();
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
async function refreshStatus() {
  const s = await api("/api/status");
  document.getElementById("status-ip").textContent = s.ip;
  document.getElementById("status-network").textContent =
    s.network_mode === "hotspot" ? "Hotspot" : s.network_mode === "client" ? "WiFi" : "—";
  document.getElementById("status-sf2").textContent = s.active_soundfont || "Nessuno";
  document.getElementById("volume-slider").value = s.volume;
  document.getElementById("volume-value").textContent = s.volume;
}

// --- SoundFonts ---
async function refreshSoundfonts() {
  const { soundfonts } = await api("/api/soundfonts");
  const list = document.getElementById("sf2-list");
  list.innerHTML = "";
  if (!soundfonts.length) {
    list.innerHTML = '<p style="color:var(--muted)">Nessun SoundFont caricato</p>';
    return;
  }
  soundfonts.forEach((sf) => {
    const div = document.createElement("div");
    div.className = "sf2-item";
    const sizeMB = (sf.size / 1024 / 1024).toFixed(1);
    div.innerHTML = `
      <div>
        <span class="sf2-name">${sf.name}</span>
        <span style="color:var(--muted);font-size:0.8rem;margin-left:0.5rem">${sizeMB} MB</span>
        ${sf.active ? '<span class="sf2-active"> ● attivo</span>' : ""}
      </div>
      <div class="sf2-actions">
        ${!sf.active ? `<button class="btn btn-secondary" data-load="${sf.name}">Carica</button>` : ""}
        <button class="btn btn-danger" data-del="${sf.name}">Elimina</button>
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

async function uploadFile(file) {
  if (!file.name.toLowerCase().endsWith(".sf2")) return alert("Solo file .sf2");
  const prog = document.getElementById("upload-progress");
  const bar = prog.querySelector(".progress-bar");
  prog.classList.remove("hidden");
  bar.style.width = "30%";

  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/soundfonts/upload", { method: "POST", body: form, credentials: "same-origin" });
  bar.style.width = "100%";
  if (!res.ok) { const d = await res.json(); alert(d.error || "Upload fallito"); }
  else refreshSoundfonts();
  setTimeout(() => { prog.classList.add("hidden"); bar.style.width = "0%"; }, 1000);
  fileInput.value = "";
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
  const { networks } = await api("/api/wifi/scan");
  const list = document.getElementById("wifi-list");
  list.innerHTML = "";
  networks.forEach((n) => {
    const div = document.createElement("div");
    div.className = "wifi-item";
    div.innerHTML = `<span>${n.ssid}</span><span class="wifi-signal">${n.signal}% ${n.security ? "🔒" : ""}</span>`;
    div.addEventListener("click", () => showWifiForm(n.ssid));
    list.appendChild(div);
  });
});

function showWifiForm(ssid) {
  const list = document.getElementById("wifi-list");
  const form = document.createElement("div");
  form.className = "wifi-form";
  form.innerHTML = `
    <p>Connetti a <strong>${ssid}</strong></p>
    <input type="password" id="wifi-password" placeholder="Password WiFi">
    <button class="btn btn-primary" id="wifi-connect-btn">Connetti</button>`;
  list.prepend(form);
  document.getElementById("wifi-connect-btn").addEventListener("click", async () => {
    const pw = document.getElementById("wifi-password").value;
    try {
      await api("/api/wifi/connect", { method: "POST", body: JSON.stringify({ ssid, password: pw }) });
      alert("Connesso! Il dispositivo si collegherà a questa rete al prossimo avvio.");
      refreshStatus();
    } catch (err) { alert(err.message); }
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
  const { authenticated } = await api("/api/auth/check");
  authenticated ? showDashboard() : showLogin();
})();

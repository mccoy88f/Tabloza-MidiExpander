const I18N = {
  it: {
    appTitle: "Tabloza MidiExpander",
    loginSubtitle: "Pannello di controllo",
    password: "Password",
    login: "Accedi",
    logout: "Esci",
    sectionStatus: "Stato",
    labelAddress: "Indirizzo",
    labelIp: "IP",
    labelNetwork: "Rete",
    labelActiveSf2: "SF2 attivo",
    labelMidiInputs: "Ingressi MIDI",
    midiReset: "MIDI Reset",
    midiResetConfirm: "Riavviare FluidSynth e ricaricare tutto il routing MIDI?",
    midiResetInProgress: "Reset in corso…",
    midiResetWorking: "Riavvio rtpmidid e FluidSynth…",
    midiResetDone: "FluidSynth e routing MIDI riavviati",
    sectionVolume: "Volume Master",
    sectionSoundfonts: "Libreria SoundFont",
    uploadDrag: "Trascina un file .sf2 qui",
    chooseFile: "Scegli file",
    sectionWifi: "WiFi",
    scanNetworks: "Scansiona reti",
    sectionSecurity: "Sicurezza",
    currentPassword: "Password attuale",
    newPassword: "Nuova password",
    changePassword: "Cambia password",
    passwordUpdated: "Password aggiornata",
    networkHotspot: "Hotspot",
    networkWifi: "WiFi",
    networkUnknown: "—",
    noSoundfont: "Nessuno",
    noMidiInputs: "Nessun ingresso rilevato",
    badgePlanned: "In arrivo",
    badgeActive: "Attivo",
    badgeSynth: "Synth",
    midiGpioName: "MIDI GPIO (UART)",
    noSoundfontsLoaded: "Nessun SoundFont caricato",
    sf2Active: "● attivo",
    load: "Carica",
    delete: "Elimina",
    deleteConfirm: "Eliminare {name}?",
    sf2Only: "Solo file .sf2",
    uploading: "Caricamento {name}…",
    uploadingPct: "Caricamento {pct}%",
    uploadDone: "{name} caricato e attivato",
    uploadFailed: "Upload fallito",
    uploadNetworkError: "Errore di rete durante l'upload",
    scanningWifi: "Scansione in corso…",
    noNetworks: "Nessuna rete trovata",
    connectTo: "Connetti a",
    wifiPassword: "Password WiFi",
    connect: "Connetti",
    connecting: "Connessione in corso…",
    connectedWifi: "Connesso a {ssid}. Al prossimo boot il dispositivo userà questa rete.",
    authRequired: "Non autenticato",
    errorGeneric: "Errore {code}",
    langIt: "IT",
    langEn: "EN",
    footerCredits: "mccoy88f su GitHub",
  },
  en: {
    appTitle: "Tabloza MidiExpander",
    loginSubtitle: "Control panel",
    password: "Password",
    login: "Sign in",
    logout: "Sign out",
    sectionStatus: "Status",
    labelAddress: "Address",
    labelIp: "IP",
    labelNetwork: "Network",
    labelActiveSf2: "Active SF2",
    labelMidiInputs: "MIDI inputs",
    midiReset: "MIDI Reset",
    midiResetConfirm: "Restart FluidSynth and reload all MIDI routing?",
    midiResetInProgress: "Resetting…",
    midiResetWorking: "Restarting rtpmidid and FluidSynth…",
    midiResetDone: "FluidSynth and MIDI routing restarted",
    sectionVolume: "Master Volume",
    sectionSoundfonts: "SoundFont Library",
    uploadDrag: "Drop a .sf2 file here",
    chooseFile: "Choose file",
    sectionWifi: "WiFi",
    scanNetworks: "Scan networks",
    sectionSecurity: "Security",
    currentPassword: "Current password",
    newPassword: "New password",
    changePassword: "Change password",
    passwordUpdated: "Password updated",
    networkHotspot: "Hotspot",
    networkWifi: "WiFi",
    networkUnknown: "—",
    noSoundfont: "None",
    noMidiInputs: "No inputs detected",
    badgePlanned: "Coming soon",
    badgeActive: "Active",
    badgeSynth: "Synth",
    midiGpioName: "MIDI GPIO (UART)",
    noSoundfontsLoaded: "No SoundFonts loaded",
    sf2Active: "● active",
    load: "Load",
    delete: "Delete",
    deleteConfirm: "Delete {name}?",
    sf2Only: ".sf2 files only",
    uploading: "Uploading {name}…",
    uploadingPct: "Uploading {pct}%",
    uploadDone: "{name} uploaded and activated",
    uploadFailed: "Upload failed",
    uploadNetworkError: "Network error during upload",
    scanningWifi: "Scanning…",
    noNetworks: "No networks found",
    connectTo: "Connect to",
    wifiPassword: "WiFi password",
    connect: "Connect",
    connecting: "Connecting…",
    connectedWifi: "Connected to {ssid}. The device will use this network on next boot.",
    authRequired: "Not authenticated",
    errorGeneric: "Error {code}",
    langIt: "IT",
    langEn: "EN",
    footerCredits: "mccoy88f on GitHub",
  },
};

const LANG_KEY = "tabloza-lang";

function getLang() {
  const stored = localStorage.getItem(LANG_KEY);
  if (stored && I18N[stored]) return stored;
  const browser = (navigator.language || "it").startsWith("it") ? "it" : "en";
  return browser;
}

function setLang(lang) {
  if (!I18N[lang]) return;
  localStorage.setItem(LANG_KEY, lang);
  document.documentElement.lang = lang;
  applyI18n();
  document.dispatchEvent(new CustomEvent("tabloza:lang", { detail: { lang } }));
}

function t(key, params = {}) {
  const lang = getLang();
  let str = I18N[lang][key] || I18N.it[key] || key;
  Object.entries(params).forEach(([k, v]) => {
    str = str.replace(`{${k}}`, v);
  });
  return str;
}

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (key) el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    if (key) el.placeholder = t(key);
  });
  document.title = t("appTitle");
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lang === getLang());
  });
}

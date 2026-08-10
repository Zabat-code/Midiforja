// main.js - Midiforja frontend logic (audio/video + sheet OMR).
import { t, getLang, setLang } from "./i18n.js";

const API = "http://127.0.0.1:8000";

const els = {
  title: document.getElementById("app_title"),
  subtitle: document.getElementById("app_subtitle"),
  langLabel: document.getElementById("lang_label"),
  langSelect: document.getElementById("lang_select"),
  // tabs
  tabAudio: document.getElementById("tab_audio"),
  tabSheet: document.getElementById("tab_sheet"),
  panelAudio: document.getElementById("panel_audio"),
  panelSheet: document.getElementById("panel_sheet"),
  // audio drop
  drop: document.getElementById("drop"),
  dropTitle: document.getElementById("drop_title"),
  dropHint: document.getElementById("drop_hint"),
  dropMax: document.getElementById("max_size"),
  fileInput: document.getElementById("file_input"),
  btn: document.getElementById("transcribe_btn"),
  btnText: document.getElementById("button_transcribe"),
  // sheet drop
  dropSheet: document.getElementById("drop_sheet"),
  sheetTitle: document.getElementById("sheet_title"),
  sheetHint: document.getElementById("sheet_hint"),
  sheetInput: document.getElementById("sheet_input"),
  sheetBtn: document.getElementById("transcribe_sheet_btn"),
  sheetBtnText: document.getElementById("button_transcribe_sheet"),
  // shared
  progress: document.getElementById("progress"),
  barFill: document.getElementById("bar_fill"),
  status: document.getElementById("status_text"),
  resultActions: document.getElementById("result_actions"),
  openMidiBtn: document.getElementById("open_midimate_btn"),
  againBtn: document.getElementById("again_btn"),
  midimateUrl: document.getElementById("midimate_url"),
  tip: document.getElementById("tip"),
  footer: document.getElementById("footer"),
};

let selectedFile = null;     // audio/video
let selectedSheet = null;    // image/pdf
let busy = false;
let lastMidiBlob = null;     // for "Open in MidiMate"

const ALLOWED_AUDIO = [
  "mp3", "wav", "ogg", "flac", "m4a", "aac",
  "mp4", "webm", "mov", "avi", "mkv", "wma",
];
const ALLOWED_SHEET = ["png", "jpg", "jpeg", "pdf", "tiff", "bmp", "gif"];

function applyI18n() {
  const lang = getLang();
  document.documentElement.lang = lang;
  els.title.textContent = t("app_title");
  els.subtitle.textContent = t("app_subtitle");
  els.langLabel.textContent = t("lang_label");
  els.dropTitle.textContent = t("drop_title");
  els.dropHint.textContent = t("drop_hint");
  els.dropMax.textContent = t("max_size");
  els.btnText.textContent = t("button_transcribe");
  els.sheetTitle.textContent = t("sheet_title");
  els.sheetHint.textContent = t("sheet_hint");
  els.sheetBtnText.textContent = t("button_transcribe_sheet");
  els.openMidiBtn.querySelector("span").textContent = t("button_open_midimate");
  els.againBtn.querySelector("span").textContent = t("button_again");
  els.tip.textContent = t("tip");
  els.footer.textContent = t("footer");
  els.langSelect.value = lang;
  document.getElementById("tab_audio_label").textContent = t("tab_audio_label");
  document.getElementById("tab_sheet_label").textContent = t("tab_sheet_label");
  document.getElementById("settings_summary").textContent = t("settings_summary");
  document.getElementById("settings_midimate_url").textContent = t("settings_midimate_url");
  document.getElementById("settings_hint").textContent = t("settings_hint");
  if (!busy) setStatus("status_idle");
}

function setStatus(key, extra = "") {
  els.status.textContent = t(key) + extra;
}
function setProgress(pct) {
  els.progress.hidden = false;
  els.barFill.style.width = pct + "%";
}
function toast(msg) {
  els.status.textContent = msg;
  setTimeout(() => { if (!busy) setStatus("status_idle"); }, 4000);
}

// ---- Tabs ----
function switchTab(which) {
  const audio = which === "audio";
  els.tabAudio.classList.toggle("active", audio);
  els.tabSheet.classList.toggle("active", !audio);
  els.panelAudio.hidden = !audio;
  els.panelSheet.hidden = audio;
}
els.tabAudio.addEventListener("click", () => switchTab("audio"));
els.tabSheet.addEventListener("click", () => switchTab("sheet"));

// ---- Audio/video ----
function pickFile(file) {
  if (!file) return;
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (!ALLOWED_AUDIO.includes(ext)) {
    selectedFile = null;
    els.btn.disabled = true;
    setStatus("status_error", t("err_unsupported"));
    return;
  }
  selectedFile = file;
  els.btn.disabled = false;
  els.dropTitle.textContent = file.name;
  els.dropHint.textContent = (file.size / (1024 * 1024)).toFixed(1) + " MB";
}

els.drop.addEventListener("click", () => els.fileInput.click());
els.drop.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") els.fileInput.click();
});
els.fileInput.addEventListener("change", (e) => pickFile(e.target.files[0]));
["dragover", "dragenter"].forEach((ev) =>
  els.drop.addEventListener(ev, (e) => { e.preventDefault(); els.drop.classList.add("drag"); })
);
["dragleave", "drop"].forEach((ev) =>
  els.drop.addEventListener(ev, (e) => { e.preventDefault(); els.drop.classList.remove("drag"); })
);
els.drop.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files && e.dataTransfer.files[0];
  pickFile(f);
});

// ---- Sheet (OMR) ----
function pickSheet(file) {
  if (!file) return;
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (!ALLOWED_SHEET.includes(ext)) {
    selectedSheet = null;
    els.sheetBtn.disabled = true;
    setStatus("status_error", t("err_sheet_unsupported"));
    return;
  }
  selectedSheet = file;
  els.sheetBtn.disabled = false;
  els.sheetTitle.textContent = file.name;
  els.sheetHint.textContent = (file.size / (1024 * 1024)).toFixed(1) + " MB";
}
els.dropSheet.addEventListener("click", () => els.sheetInput.click());
els.dropSheet.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") els.sheetInput.click();
});
els.sheetInput.addEventListener("change", (e) => pickSheet(e.target.files[0]));
["dragover", "dragenter"].forEach((ev) =>
  els.dropSheet.addEventListener(ev, (e) => { e.preventDefault(); els.dropSheet.classList.add("drag"); })
);
["dragleave", "drop"].forEach((ev) =>
  els.dropSheet.addEventListener(ev, (e) => { e.preventDefault(); els.dropSheet.classList.remove("drag"); })
);
els.dropSheet.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files && e.dataTransfer.files[0];
  pickSheet(f);
});

// ---- Shared reset ----
function resetForNewFile() {
  busy = false;
  selectedFile = null;
  selectedSheet = null;
  lastMidiBlob = null;
  els.fileInput.value = "";
  els.sheetInput.value = "";
  els.btn.disabled = true;
  els.sheetBtn.disabled = true;
  els.btnText.textContent = t("button_transcribe");
  els.sheetBtnText.textContent = t("button_transcribe_sheet");
  els.resultActions.hidden = true;
  els.dropTitle.textContent = t("drop_title");
  els.dropHint.textContent = t("drop_hint");
  els.sheetTitle.textContent = t("sheet_title");
  els.sheetHint.textContent = t("sheet_hint");
  setProgress(0);
  els.progress.hidden = true;
  setStatus("status_idle");
}

// ---- Transcribe audio/video ----
els.btn.addEventListener("click", async () => {
  if (busy) { resetForNewFile(); return; }
  if (!selectedFile) { setStatus("status_error", t("err_no_file")); return; }
  busy = true;
  els.btn.disabled = true;
  els.resultActions.hidden = true;
  setProgress(10);
  setStatus("status_uploading");
  try {
    const fd = new FormData();
    fd.append("file", selectedFile, selectedFile.name);
    const resp = await fetch(API + "/api/transcribe", { method: "POST", body: fd });
    if (!resp.ok) {
      let msg = t("err_generic");
      try { const j = await resp.json(); if (j && j.detail) msg = mapError(j.detail); } catch (_) {}
      if (resp.status === 422 && /no se detectaron|no notes/i.test(msg)) msg = t("err_no_notes");
      if (resp.status === 422 && /ffmpeg/i.test(msg)) msg = t("err_ffmpeg");
      setStatus("status_error", msg);
      busy = false; els.btn.disabled = false; els.btnText.textContent = t("button_transcribe");
      return;
    }
    setProgress(70); setStatus("status_processing");
    const blob = await resp.blob();
    const noteCount = resp.headers.get("X-Note-Count") || "?";
    lastMidiBlob = blob;
    downloadBlob(blob, "midiforja_output.mid");
    setProgress(100); setStatus("status_done");
    els.status.textContent += `  (${noteCount} ${t("note_count")})`;
    els.resultActions.hidden = false;
  } catch (err) {
    setStatus("status_error", t("err_generic") + " " + (err.message || ""));
  } finally {
    busy = false; els.btn.disabled = false; els.btnText.textContent = t("button_again");
  }
});

// ---- Transcribe sheet (OMR) ----
els.sheetBtn.addEventListener("click", async () => {
  if (busy) { resetForNewFile(); return; }
  if (!selectedSheet) { setStatus("status_error", t("err_no_file")); return; }
  busy = true;
  els.sheetBtn.disabled = true;
  els.resultActions.hidden = true;
  setProgress(10);
  setStatus("status_uploading");
  try {
    const fd = new FormData();
    fd.append("file", selectedSheet, selectedSheet.name);
    const resp = await fetch(API + "/api/transcribe-sheet", { method: "POST", body: fd });
    if (!resp.ok) {
      let msg = t("err_generic");
      try { const j = await resp.json(); if (j && j.detail) msg = mapError(j.detail); } catch (_) {}
      if (/Audiveris/i.test(msg)) msg = t("err_audiveris");
      if (resp.status === 422 && /no soportado/i.test(msg)) msg = t("err_sheet_unsupported");
      setStatus("status_error", msg);
      busy = false; els.sheetBtn.disabled = false; els.sheetBtnText.textContent = t("button_transcribe_sheet");
      return;
    }
    setProgress(70); setStatus("status_processing");
    const blob = await resp.blob();
    const noteCount = resp.headers.get("X-Note-Count") || "?";
    lastMidiBlob = blob;
    downloadBlob(blob, "midiforja_sheet.mid");
    setProgress(100); setStatus("status_done");
    els.status.textContent += `  (${noteCount} ${t("note_count")})`;
    els.resultActions.hidden = false;
  } catch (err) {
    setStatus("status_error", t("err_generic") + " " + (err.message || ""));
  } finally {
    busy = false; els.sheetBtn.disabled = false; els.sheetBtnText.textContent = t("button_again");
  }
});

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

// ---- Open in MidiMate ----
els.againBtn.addEventListener("click", () => resetForNewFile());
els.openMidiBtn.addEventListener("click", async () => {
  if (!lastMidiBlob) { toast(t("err_no_file")); return; }
  const url = (els.midimateUrl.value || "http://localhost:5173").trim();
  try {
    const fd = new FormData();
    fd.append("file", lastMidiBlob, "midiforja_output.mid");
    const resp = await fetch(API + "/api/send-to-midimate", { method: "POST", body: fd });
    const j = await resp.json().catch(() => ({}));
    if (!resp.ok || !j.ok) {
      setStatus("status_error", t("err_send") + (j.detail || resp.status));
      return;
    }
    window.open(url, "_blank");
    toast(t("toast_sent"));
  } catch (err) {
    setStatus("status_error", t("err_send") + (err.message || ""));
  }
});

function mapError(detail) {
  if (/no soportado|unsupported/i.test(detail)) return t("err_unsupported");
  if (/demasiado grande|too large/i.test(detail)) return t("err_generic") + " (200 MB)";
  if (/ffmpeg/i.test(detail)) return t("err_ffmpeg");
  if (/detectaron|detected/i.test(detail)) return t("err_no_notes");
  if (/Audiveris/i.test(detail)) return t("err_audiveris");
  return detail;
}

els.langSelect.addEventListener("change", (e) => { setLang(e.target.value); applyI18n(); });

applyI18n();

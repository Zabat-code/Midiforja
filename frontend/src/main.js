// main.js - Midiforja frontend logic (audio/video, sheet OMR, MIDI analysis).
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
  tabMidi: document.getElementById("tab_midi"),
  panelAudio: document.getElementById("panel_audio"),
  panelSheet: document.getElementById("panel_sheet"),
  panelMidi: document.getElementById("panel_midi"),
  // audio drop
  drop: document.getElementById("drop"),
  dropTitle: document.getElementById("drop_title"),
  dropHint: document.getElementById("drop_hint"),
  dropMax: document.getElementById("max_size"),
  fileInput: document.getElementById("file_input"),
  btn: document.getElementById("transcribe_btn"),
  btnText: document.getElementById("button_transcribe"),
  optVocals: document.getElementById("opt_vocals"),
  optQuantize: document.getElementById("opt_quantize"),
  optVocalsLabel: document.getElementById("opt_vocals_label"),
  optQuantizeLabel: document.getElementById("opt_quantize_label"),
  // sheet drop
  dropSheet: document.getElementById("drop_sheet"),
  sheetTitle: document.getElementById("sheet_title"),
  sheetHint: document.getElementById("sheet_hint"),
  sheetInput: document.getElementById("sheet_input"),
  sheetBtn: document.getElementById("transcribe_sheet_btn"),
  sheetBtnText: document.getElementById("button_transcribe_sheet"),
  // midi analysis
  dropMidi: document.getElementById("drop_midi"),
  midiTitle: document.getElementById("midi_title"),
  midiHint: document.getElementById("midi_hint"),
  midiInput: document.getElementById("midi_input"),
  midiBtn: document.getElementById("analyze_btn"),
  midiBtnText: document.getElementById("button_analyze"),
  analysisResult: document.getElementById("analysis_result"),
  analysisHeading: document.getElementById("analysis_heading"),
  analysisBadge: document.getElementById("analysis_badge"),
  analysisSummary: document.getElementById("analysis_summary"),
  analysisChords: document.getElementById("analysis_chords"),
  downloadPackBtn: document.getElementById("download_pack_btn"),
  downloadPackText: document.getElementById("button_download_pack"),
  downloadMidiBtn: document.getElementById("download_midi_btn"),
  downloadMidiText: document.getElementById("button_download_midi"),
  // library
  libraryTitle: document.getElementById("library_title"),
  libraryStats: document.getElementById("library_stats"),
  librarySearch: document.getElementById("library_search"),
  libraryKind: document.getElementById("library_kind"),
  libraryKey: document.getElementById("library_key"),
  libraryList: document.getElementById("library_list"),
  refreshLibraryBtn: document.getElementById("refresh_library_btn"),
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

let selectedFile = null;
let selectedSheet = null;
let selectedMidi = null;
let busy = false;
let lastMidiBlob = null;
let lastPack = null;
let libraryItems = [];

const ALLOWED_AUDIO = [
  "mp3", "wav", "ogg", "opus", "flac", "m4a", "aac",
  "mp4", "webm", "mov", "avi", "mkv", "wma",
];
const ALLOWED_SHEET = ["png", "jpg", "jpeg", "pdf", "tiff", "bmp", "gif"];

function applyI18n() {
  const lang = getLang();
  document.documentElement.lang = lang;
  els.title.textContent = t("app_title");
  els.subtitle.textContent = t("app_subtitle");
  els.langLabel.textContent = t("lang_label");
  els.dropTitle.textContent = selectedFile ? selectedFile.name : t("drop_title");
  els.dropHint.textContent = t("drop_hint");
  els.dropMax.textContent = t("max_size");
  els.btnText.textContent = t("button_transcribe");
  els.optVocalsLabel.textContent = t("opt_vocals_label");
  els.optQuantizeLabel.textContent = t("opt_quantize_label");
  els.sheetTitle.textContent = selectedSheet ? selectedSheet.name : t("sheet_title");
  els.sheetHint.textContent = t("sheet_hint");
  els.sheetBtnText.textContent = t("button_transcribe_sheet");
  els.midiTitle.textContent = selectedMidi ? selectedMidi.name : t("midi_title");
  els.midiHint.textContent = t("midi_hint");
  els.midiBtnText.textContent = t("button_analyze");
  els.openMidiBtn.querySelector("span").textContent = t("button_open_midimate");
  els.againBtn.querySelector("span").textContent = t("button_again");
  els.downloadPackText.textContent = t("button_download_pack");
  els.downloadMidiText.textContent = t("button_download_midi");
  els.analysisHeading.textContent = t("analysis_heading");
  els.libraryTitle.textContent = t("library_title");
  els.librarySearch.placeholder = t("library_search");
  els.libraryKind.options[0].textContent = t("library_kind_all");
  els.libraryKey.options[0].textContent = t("library_key_all");
  els.tip.textContent = t("tip");
  els.footer.textContent = t("footer");
  els.langSelect.value = lang;
  document.getElementById("tab_audio_label").textContent = t("tab_audio_label");
  document.getElementById("tab_sheet_label").textContent = t("tab_sheet_label");
  document.getElementById("tab_midi_label").textContent = t("tab_midi_label");
  document.getElementById("midi_note").textContent = t("midi_note");
  document.getElementById("settings_summary").textContent = t("settings_summary");
  document.getElementById("settings_midimate_url").textContent = t("settings_midimate_url");
  document.getElementById("settings_hint").textContent = t("settings_hint");
  if (lastPack) renderAnalysis(lastPack);
  if (libraryItems.length) renderLibraryItems();
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
  const sheet = which === "sheet";
  els.tabAudio.classList.toggle("active", audio);
  els.tabSheet.classList.toggle("active", sheet);
  els.tabMidi.classList.toggle("active", which === "midi");
  els.panelAudio.hidden = !audio;
  els.panelSheet.hidden = !sheet;
  els.panelMidi.hidden = which !== "midi";
}
els.tabAudio.addEventListener("click", () => switchTab("audio"));
els.tabSheet.addEventListener("click", () => switchTab("sheet"));
els.tabMidi.addEventListener("click", () => switchTab("midi"));

// ---- Drop zones ----
function bindDrop(zone, input, onFile) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") input.click();
  });
  ["dragover", "dragenter"].forEach((ev) =>
    zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("drag"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("drag"); })
  );
  zone.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    onFile(f);
  });
  input.addEventListener("change", (e) => onFile(e.target.files[0]));
}

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

function pickMidi(file) {
  if (!file) return;
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (ext !== "mid" && ext !== "midi") {
    selectedMidi = null;
    els.midiBtn.disabled = true;
    setStatus("status_error", t("err_midi_invalid"));
    return;
  }
  selectedMidi = file;
  els.midiBtn.disabled = false;
  els.midiTitle.textContent = file.name;
  els.midiHint.textContent = (file.size / (1024 * 1024)).toFixed(2) + " MB";
}

bindDrop(els.drop, els.fileInput, pickFile);
bindDrop(els.dropSheet, els.sheetInput, pickSheet);
bindDrop(els.dropMidi, els.midiInput, pickMidi);

// ---- Shared reset ----
function resetForNewFile() {
  busy = false;
  selectedFile = null;
  selectedSheet = null;
  selectedMidi = null;
  lastMidiBlob = null;
  lastPack = null;
  els.fileInput.value = "";
  els.sheetInput.value = "";
  els.midiInput.value = "";
  els.btn.disabled = true;
  els.sheetBtn.disabled = true;
  els.midiBtn.disabled = true;
  els.btnText.textContent = t("button_transcribe");
  els.sheetBtnText.textContent = t("button_transcribe_sheet");
  els.midiBtnText.textContent = t("button_analyze");
  els.resultActions.hidden = true;
  els.analysisResult.hidden = true;
  els.dropTitle.textContent = t("drop_title");
  els.dropHint.textContent = t("drop_hint");
  els.sheetTitle.textContent = t("sheet_title");
  els.sheetHint.textContent = t("sheet_hint");
  els.midiTitle.textContent = t("midi_title");
  els.midiHint.textContent = t("midi_hint");
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
    fd.append("omit_vocals", els.optVocals.checked ? "true" : "false");
    fd.append("quantize", els.optQuantize.checked ? "true" : "false");
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
    const quality = resp.headers.get("X-Quality");
    const warning = resp.headers.get("X-Warning");
    const analysisId = resp.headers.get("X-Analysis-Id");
    const dlName = resp.headers.get("X-Filename") || "midiforja_output.mid";
    lastMidiBlob = blob;
    downloadBlob(blob, dlName);
    setProgress(100); setStatus("status_done");
    let extra = `  (${noteCount} ${t("note_count")})`;
    if (quality) extra += ` · ${t("quality_label")}${quality}`;
    if (warning) extra += `  ${t("warn_vocals")}`;
    if (analysisId) extra += ` · ${analysisId.slice(0, 8)}`;
    els.status.textContent += extra;
    els.resultActions.hidden = false;
    await refreshLibrary();
    if (analysisId) await loadAnalysis(analysisId, false);
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
    const analysisId = resp.headers.get("X-Analysis-Id");
    const dlName = resp.headers.get("X-Filename") || "midiforja_sheet.mid";
    lastMidiBlob = blob;
    downloadBlob(blob, dlName);
    setProgress(100); setStatus("status_done");
    els.status.textContent += `  (${noteCount} ${t("note_count")})`;
    els.resultActions.hidden = false;
    await refreshLibrary();
    if (analysisId) await loadAnalysis(analysisId, false);
  } catch (err) {
    setStatus("status_error", t("err_generic") + " " + (err.message || ""));
  } finally {
    busy = false; els.sheetBtn.disabled = false; els.sheetBtnText.textContent = t("button_again");
  }
});

// ---- Analyze MIDI ----
els.midiBtn.addEventListener("click", async () => {
  if (busy) { resetForNewFile(); return; }
  if (!selectedMidi) { setStatus("status_error", t("err_no_file")); return; }
  busy = true;
  els.midiBtn.disabled = true;
  els.analysisResult.hidden = true;
  setProgress(20);
  setStatus("status_analyzing");
  try {
    const fd = new FormData();
    fd.append("file", selectedMidi, selectedMidi.name);
    const resp = await fetch(API + "/api/analyze-midi", { method: "POST", body: fd });
    if (!resp.ok) {
      let msg = t("err_generic");
      try { const j = await resp.json(); if (j && j.detail) msg = mapError(j.detail); } catch (_) {}
      if (/MIDI|midi/.test(msg)) msg = t("err_midi_invalid");
      setStatus("status_error", msg);
      busy = false; els.midiBtn.disabled = false; els.midiBtnText.textContent = t("button_analyze");
      return;
    }
    const pack = await resp.json();
    setProgress(100); setStatus("status_analyzed");
    lastPack = pack;
    renderAnalysis(pack);
    await refreshLibrary();
  } catch (err) {
    setStatus("status_error", t("err_generic") + " " + (err.message || ""));
  } finally {
    busy = false; els.midiBtn.disabled = false; els.midiBtnText.textContent = t("button_analyze");
  }
});

function difficultyLabel(diff) {
  const names = {
    beginner: "difficulty_beginner", intermediate: "difficulty_intermediate",
    advanced: "difficulty_advanced", expert: "difficulty_expert",
  };
  return t(names[diff?.label] || "difficulty_intermediate");
}

function addStat(label, value) {
  const box = document.createElement("div");
  box.className = "stat";
  const l = document.createElement("span");
  l.className = "stat-label";
  l.textContent = label;
  const v = document.createElement("strong");
  v.textContent = value;
  box.append(l, v);
  els.analysisSummary.appendChild(box);
}

function renderAnalysis(pack) {
  const s = pack.summary || {};
  const a = pack.analysis || {};
  const diff = a.difficulty || {};
  const key = a.key || {};
  const rhythm = a.rhythm || {};
  els.analysisResult.hidden = false;
  els.analysisBadge.textContent = pack.id ? pack.id.slice(0, 8) : "";
  els.analysisSummary.textContent = "";
  addStat(t("analysis_notes"), String(s.note_count ?? "?"));
  addStat(t("analysis_duration"), `${Number(s.duration_sec || 0).toFixed(1)} s`);
  addStat(t("analysis_bpm"), String(Math.round(s.bpm || rhythm.bpm || 0)));
  addStat(t("analysis_key"), `${key.key || "?"} ${key.mode || ""}`.trim());
  addStat(t("analysis_chords"), String(s.unique_chords ?? 0));
  addStat(t("analysis_difficulty"), `${difficultyLabel(diff)} (${diff.score ?? "?"})`);
  addStat(t("analysis_polyphony"), String(diff.max_polyphony ?? 0));
  addStat(t("analysis_density"), String(rhythm.notes_per_second ?? 0));

  els.analysisChords.textContent = "";
  const title = document.createElement("span");
  title.className = "chord-title";
  title.textContent = t("analysis_chords") + ": ";
  els.analysisChords.appendChild(title);
  for (const item of (a.chord_frequency || []).slice(0, 10)) {
    const chip = document.createElement("span");
    chip.className = "chord-chip";
    chip.textContent = `${item.chord} ×${item.count}`;
    els.analysisChords.appendChild(chip);
  }
}

async function loadAnalysis(id, switchPane = true) {
  try {
    const resp = await fetch(`${API}/api/analyses/${encodeURIComponent(id)}`);
    if (!resp.ok) return;
    lastPack = await resp.json();
    renderAnalysis(lastPack);
    if (switchPane) {
      switchTab("midi");
      toast(t("status_analyzed"));
    }
  } catch (_) { /* silencioso: la biblioteca sigue disponible */ }
}

// ---- Biblioteca local ----
function renderLibraryItems() {
  els.libraryList.textContent = "";
  if (!libraryItems.length) {
    const empty = document.createElement("p");
    empty.className = "library-empty";
    empty.textContent = t("library_empty");
    els.libraryList.appendChild(empty);
    return;
  }
  for (const item of libraryItems) {
    const row = document.createElement("div");
    row.className = "library-row";

    const info = document.createElement("div");
    info.className = "library-info";
    const name = document.createElement("strong");
    name.textContent = item.source_name || item.id.slice(0, 8);
    const meta = document.createElement("small");
    meta.textContent = [
      item.key_name, item.key_mode, `${item.note_count} ${t("note_count")}`,
      Math.round(item.bpm || 0) + " BPM",
      (item.created_at || "").replace("T", " ").slice(0, 19),
    ].filter(Boolean).join(" · ");
    info.append(name, meta);

    const actions = document.createElement("div");
    actions.className = "library-actions";
    const view = document.createElement("button");
    view.className = "btn small";
    view.textContent = t("library_load");
    view.addEventListener("click", () => loadAnalysis(item.id));
    const packBtn = document.createElement("button");
    packBtn.className = "btn small";
    packBtn.textContent = "↓ JSON";
    packBtn.addEventListener("click", () => {
      window.open(`${API}/api/study-pack/${encodeURIComponent(item.id)}`, "_blank");
    });
    const del = document.createElement("button");
    del.className = "btn small danger";
    del.textContent = t("library_delete");
    del.addEventListener("click", async () => {
      if (!confirm(t("library_delete") + "?")) return;
      const resp = await fetch(`${API}/api/analyses/${encodeURIComponent(item.id)}`, {
        method: "DELETE",
      });
      if (resp.ok) {
        toast(t("library_deleted"));
        await refreshLibrary();
      }
    });
    actions.append(view, packBtn, del);
    row.append(info, actions);
    els.libraryList.appendChild(row);
  }
}

async function refreshLibrary() {
  try {
    const params = new URLSearchParams();
    if (els.librarySearch.value.trim()) params.set("search", els.librarySearch.value.trim());
    if (els.libraryKind.value) params.set("kind", els.libraryKind.value);
    if (els.libraryKey.value) params.set("key", els.libraryKey.value);
    const [listResp, statsResp] = await Promise.all([
      fetch(`${API}/api/analyses?${params}`),
      fetch(`${API}/api/stats`),
    ]);
    if (!listResp.ok || !statsResp.ok) return;
    const list = await listResp.json();
    const stats = await statsResp.json();
    libraryItems = list.items || [];
    renderLibraryItems();
    els.libraryStats.textContent = t("library_stats", {
      total: stats.total || 0,
      audio: stats.by_kind?.audio || 0,
      sheet: stats.by_kind?.sheet || 0,
      midi: stats.by_kind?.midi || 0,
    });

    const current = els.libraryKey.value;
    els.libraryKey.textContent = "";
    const all = document.createElement("option");
    all.value = "";
    all.textContent = t("library_key_all");
    els.libraryKey.appendChild(all);
    for (const k of Object.keys(stats.by_key || {}).sort()) {
      const opt = document.createElement("option");
      opt.value = k;
      opt.textContent = k;
      els.libraryKey.appendChild(opt);
    }
    els.libraryKey.value = current;
  } catch (_) { /* backend apagado: no rompemos la UI */ }
}

els.refreshLibraryBtn.addEventListener("click", refreshLibrary);
els.librarySearch.addEventListener("input", refreshLibrary);
els.libraryKind.addEventListener("change", refreshLibrary);
els.libraryKey.addEventListener("change", refreshLibrary);
els.downloadPackBtn.addEventListener("click", () => {
  if (lastPack) {
    window.open(`${API}/api/study-pack/${encodeURIComponent(lastPack.id)}`, "_blank");
  }
});
els.downloadMidiBtn.addEventListener("click", async () => {
  if (!lastPack) return;
  const resp = await fetch(`${API}/api/analyses/${encodeURIComponent(lastPack.id)}/midi`);
  if (!resp.ok) return;
  downloadBlob(await resp.blob(), (lastPack.source?.filename || "midiforja_output.mid").replace(/\.\w+$/, ".mid"));
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
  if (/MIDI|midi/i.test(detail)) return t("err_midi_invalid");
  return detail;
}

els.langSelect.addEventListener("change", (e) => { setLang(e.target.value); applyI18n(); });

applyI18n();
refreshLibrary();

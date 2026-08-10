// main.js - Midiforja frontend logic.
import { t, getLang, setLang } from "./i18n.js";

const API = "http://127.0.0.1:8000/api/transcribe";

const els = {
  title: document.getElementById("app_title"),
  subtitle: document.getElementById("app_subtitle"),
  langLabel: document.getElementById("lang_label"),
  langSelect: document.getElementById("lang_select"),
  drop: document.getElementById("drop"),
  dropTitle: document.getElementById("drop_title"),
  dropHint: document.getElementById("drop_hint"),
  dropMax: document.getElementById("max_size"),
  fileInput: document.getElementById("file_input"),
  btn: document.getElementById("transcribe_btn"),
  btnText: document.getElementById("button_transcribe"),
  progress: document.getElementById("progress"),
  barFill: document.getElementById("bar_fill"),
  status: document.getElementById("status_text"),
  tip: document.getElementById("tip"),
  footer: document.getElementById("footer"),
};

let selectedFile = null;
let busy = false;

const ALLOWED = [
  "mp3", "wav", "ogg", "flac", "m4a", "aac",
  "mp4", "webm", "mov", "avi", "mkv", "wma",
];

function applyI18n() {
  const lang = getLang();
  document.documentElement.lang = lang;
  els.title.textContent = t("app_title");
  els.subtitle.textContent = t("app_subtitle");
  els.langLabel.textContent = t("lang_label");
  els.dropTitle.textContent = t("drop_title");
  els.dropHint.textContent = t("drop_hint");
  els.dropMax.textContent = t("max_size");
  els.btnText.textContent = busy
    ? t("button_again")
    : (selectedFile ? t("button_transcribe") : t("button_transcribe"));
  els.tip.textContent = t("tip");
  els.footer.textContent = t("footer");
  els.langSelect.value = lang;
  if (!busy) setStatus("status_idle");
}

function setStatus(key, extra = "") {
  els.status.textContent = t(key) + extra;
}

function setProgress(pct) {
  els.progress.hidden = false;
  els.barFill.style.width = pct + "%";
}

function resetAfterDone() {
  busy = false;
  selectedFile = null;
  els.fileInput.value = "";
  els.btn.disabled = true;
  els.btnText.textContent = t("button_again");
  els.dropTitle.textContent = t("drop_title");
  els.dropHint.textContent = t("drop_hint");
  setProgress(0);
  els.progress.hidden = true;
}

function pickFile(file) {
  if (!file) return;
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (!ALLOWED.includes(ext)) {
    selectedFile = null;
    els.btn.disabled = true;
    setStatus("status_error", t("err_unsupported"));
    return;
  }
  selectedFile = file;
  els.btn.disabled = false;
  els.dropTitle.textContent = file.name;
  els.dropHint.textContent = (file.size / (1024 * 1024)).toFixed(1) + " MB";
  setStatus("status_idle");
}

// ---- Events ----
els.drop.addEventListener("click", () => els.fileInput.click());
els.drop.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") els.fileInput.click();
});
els.fileInput.addEventListener("change", (e) => pickFile(e.target.files[0]));

["dragover", "dragenter"].forEach((ev) =>
  els.drop.addEventListener(ev, (e) => {
    e.preventDefault();
    els.drop.classList.add("drag");
  })
);
["dragleave", "drop"].forEach((ev) =>
  els.drop.addEventListener(ev, (e) => {
    e.preventDefault();
    els.drop.classList.remove("drag");
  })
);
els.drop.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files && e.dataTransfer.files[0];
  pickFile(f);
});

els.langSelect.addEventListener("change", (e) => {
  setLang(e.target.value);
  applyI18n();
});

els.btn.addEventListener("click", async () => {
  if (busy) {
    resetAfterDone();
    return;
  }
  if (!selectedFile) {
    setStatus("status_error", t("err_no_file"));
    return;
  }
  busy = true;
  els.btn.disabled = true;
  setProgress(10);
  setStatus("status_uploading");

  try {
    const fd = new FormData();
    fd.append("file", selectedFile, selectedFile.name);

    const resp = await fetch(API, { method: "POST", body: fd });

    if (!resp.ok) {
      let msg = t("err_generic");
      try {
        const j = await resp.json();
        if (j && j.detail) msg = j.detail;
      } catch (_) {}
      if (resp.status === 422) msg = t("err_no_notes");
      setStatus("status_error", msg);
      busy = false;
      els.btn.disabled = false;
      els.btnText.textContent = t("button_again");
      return;
    }

    setProgress(70);
    setStatus("status_processing");

    const blob = await resp.blob();
    const noteCount = resp.headers.get("X-Note-Count") || "?";

    // Trigger download.
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "midiforja_output.mid";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    setProgress(100);
    setStatus("status_done");
    els.status.textContent += `  (${noteCount} ${t("note_count")})`;
  } catch (err) {
    setStatus("status_error", t("err_generic") + " " + (err.message || ""));
  } finally {
    busy = false;
    els.btn.disabled = false;
    els.btnText.textContent = t("button_again");
  }
});

applyI18n();

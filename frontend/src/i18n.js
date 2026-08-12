// i18n.js - ES/EN string tables for Midiforja. Switchable at runtime.

const STRINGS = {
  es: {
    app_title: "Midiforja",
    app_subtitle: "Convierte audio o video en MIDI (enfocado en piano)",
    lang_label: "Idioma",
    drop_title: "Suelta aquí tu audio o video",
    drop_hint: "o haz clic para elegir · mp3, wav, mp4, webm, ogg, flac, m4a…",
    max_size: "Tamaño máximo: 200 MB",
    button_transcribe: "Transcribir a MIDI",
    opt_vocals_label: "Eliminar la voz (si canta alguien)",
    opt_quantize_label: "Ajustar ritmo a la grilla (cuantizar)",
    quality_label: "Calidad de ritmo: ",
    warn_vocals: "Aviso: Demucs no está instalado, no se pudo eliminar la voz.",
    button_again: "Transcribir otro",
    button_open_midimate: "Abrir en MidiMate",
    settings_summary: "Ajustes",
    settings_midimate_url: "URL de MidiMate",
    settings_hint: '"Abrir en MidiMate" copia el .mid en la carpeta de MidiMate y abre la app.',
    status_idle: "Listo.",
    status_uploading: "Subiendo…",
    status_processing: "Transcribiendo (esto puede tardar en CPU)…",
    status_done: "¡Listo! Descargando MIDI.",
    status_error: "Error: ",
    err_no_file: "No se seleccionó archivo.",
    err_unsupported: "Tipo de archivo no soportado.",
    err_no_notes: "No se detectaron notas. Prueba con una grabación más clara de un solo instrumento (piano).",
    err_ffmpeg: "No se pudo extraer el audio (¿el archivo tiene pista de audio?).",
    err_generic: "Fallo inesperado.",
    err_send: "No se pudo copiar a MidiMate: ",
    note_count: "notas detectadas",
    toast_sent: "Copiado a MidiMate. Suéltalo en la app.",
    tab_audio_label: "Audio / Video",
    tab_sheet_label: "Partitura",
    sheet_title: "Suelta aquí una imagen o PDF de partitura",
    sheet_hint: "PNG, JPG o PDF (una página sola funciona mejor)",
    button_transcribe_sheet: "Convertir partitura a MIDI",
    err_sheet_unsupported: "Tipo de archivo no soportado para partitura (usa PNG/JPG/PDF).",
    err_audiveris: "Audiveris no está instalado. Instálalo para usar OMR de partituras.",
    footer: "Motor: Basic Pitch (Spotify, Apache-2.0) + Audiveris (OMR). El .mid resultante es compatible con MidiMate y cualquier DAW.",
    tip: "Consejo: Basic Pitch funciona mejor con UN instrumento a la vez. Audiveris (partitura) necesita una imagen/PDF nítida de la partitura.",
  },
  en: {
    app_title: "Midiforja",
    app_subtitle: "Turn audio or video into MIDI (piano-focused)",
    lang_label: "Language",
    drop_title: "Drop your audio or video here",
    drop_hint: "or click to choose · mp3, wav, mp4, webm, ogg, flac, m4a…",
    max_size: "Max size: 200 MB",
    button_transcribe: "Transcribe to MIDI",
    opt_vocals_label: "Remove vocals (if someone sings)",
    opt_quantize_label: "Snap rhythm to beat grid (quantize)",
    quality_label: "Rhythm quality: ",
    warn_vocals: "Note: Demucs not installed, couldn't remove vocals.",
    button_again: "Transcribe another",
    button_open_midimate: "Open in MidiMate",
    settings_summary: "Settings",
    settings_midimate_url: "MidiMate URL",
    settings_hint: '"Open in MidiMate" copies the .mid into MidiMate\'s folder and opens the app.',
    status_idle: "Ready.",
    status_uploading: "Uploading…",
    status_processing: "Transcribing (may be slow on CPU)…",
    status_done: "Done! Downloading MIDI.",
    status_error: "Error: ",
    err_no_file: "No file selected.",
    err_unsupported: "Unsupported file type.",
    err_no_notes: "No notes detected. Try a clearer single-instrument (piano) recording with less background noise.",
    err_ffmpeg: "Could not extract audio (does the file have an audio track?).",
    err_generic: "Unexpected failure.",
    err_send: "Could not copy to MidiMate: ",
    note_count: "notes detected",
    toast_sent: "Copied to MidiMate. Drop it into the app.",
    tab_audio_label: "Audio / Video",
    tab_sheet_label: "Sheet",
    sheet_title: "Drop a sheet music image or PDF here",
    sheet_hint: "PNG, JPG or PDF (a single page works best)",
    button_transcribe_sheet: "Convert sheet to MIDI",
    err_sheet_unsupported: "Unsupported file type for sheet (use PNG/JPG/PDF).",
    err_audiveris: "Audiveris is not installed. Install it to use sheet OMR.",
    footer: "Engine: Basic Pitch (Spotify, Apache-2.0) + Audiveris (OMR). The resulting .mid is compatible with MidiMate and any DAW.",
    tip: "Tip: Basic Pitch works best with ONE instrument at a time. Audiveris (sheet) needs a clear image/PDF of the score.",
  },
};

let current = localStorage.getItem("midiforja_lang") || "es";

export function getLang() {
  return current;
}

export function setLang(lang) {
  current = lang;
  localStorage.setItem("midiforja_lang", lang);
}

export function t(key) {
  return (STRINGS[current] && STRINGS[current][key]) || key;
}

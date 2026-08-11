# Midiforja — Plan (actualizado al día)

App para convertir audio/video en MIDI, y (fase futura) partituras en imagen/PDF.
Nombre libre en GitHub ("Midiforja"/"MidiForja" = 404, sin colisión). Licencia MIT.
Motor de transcripción: Spotify Basic Pitch (Apache-2.0).

---

## Cómo empezó vs cómo quedó

- **Plan inicial acordado**: solo audio/video→MIDI, app separada mínima, sin OMR por ahora,
  basic-pitch, i18n ES/EN con switch, integración MidiMate manual (descargar .mid).
- **Base "adveris"**: el usuario creyó tener un repo clonado de "adveris". No existía en
  ia.proyectos; el único `adveris/*` en GitHub es un plugin de Figma (irrelevante). Se descartó
  y se creó Midiforja desde cero.
- **Sorpresa de instalación**: basic-pitch 0.4.0 arrastra TensorFlow 2.15 (~1.2 GB); la
  instalación tardó ~15 min en esta conexión. La API cambió: `basic_pitch.api.predict` ya no
  existe; el correcto es `basic_pitch.inference.predict(...)` que devuelve
  `(model_output, midi_data, note_events)`. Se corrigió en server.py.
- **Verificación real (no inventada)**: WAV de piano sintético (C4..C5, 8 notas) →
  `/api/transcribe` → Basic Pitch detectó **8 notas** → `.mid` aceptado por el parser REAL de
  MidiMate (`src/midi.js`): `ticksPerBeat:480, tracks:2, noteCount:8`, con C4/D4/E4 a tiempos y
  velocidades correctos.

---

## Estado actual (verificado)

Hecho y funcionando:
- Backend FastAPI (Python 3.11 venv en `.venv/`) en `:8000`: `/`, `/api/info`,
  `/api/transcribe` (ffmpeg audio/video→WAV mono 44.1k → basic-pitch → `.mid`).
- Frontend Vite (vanilla JS) en `:5174`: drag&drop, barra de progreso, descarga de `.mid`,
  i18n ES/EN con selector.
- `midiwriter.py`: Standard MIDI File tipo 1, `ticksPerBeat=480`, tempo 120 BPM, notas en ticks
  reales (segundos) → suena a velocidad correcta. Compatible con MidiMate.
- Repo git limpio, commiteado (`e58dbac`, `69f851e`, `3bb47bf`), `.venv/` ignorado.
- Límites: 200 MB por archivo, formatos comunes de audio/video.

NO hecho / pendiente:
- **OMR (Fase B)**: OPERATIVO. Audiveris 5.11 quedó instalado en `C:\Program Files\Audiveris`
  y el auto-detect de `server.py` ahora lo encuentra (`Audiveris.exe`, no solo `bin/audiveris.bat`).
  El endpoint `/api/transcribe-sheet` + `musicxml2midi.py` + pestaña "Partitura" funcionan
  end-to-end (verificado: PNG de prueba → .mxl → .mid válido, HTTP 200). Si Audiveris no se
  detecta, define `MIDIFORJA_AUDIVERIS_BIN`. Nota: el `.mxl` de Audiveris es un ZIP; `_read_musicxml`
  lo descomprime.
- **Multi-instrumento real (Fase C)**: Basic Pitch NO separa instrumentos. Requiere
  source separation (Demucs/PyTorch) antes de Basic Pitch. Pesado en CPU. Pendiente.
- **Suite de tests automática (pytest)**: HECHA (9 passed) en `backend/tests/`.
- **Deep-link "Abrir en MidiMate"**: HECHO (copia .mid a MidiMate/midiforja_inbox y abre la app).

---

## Sobre "varias pistas / varios instrumentos" (tu duda original)

Respuesta honesta: **Basic Pitch NO asimila pistas de varios instrumentos por separado.**
- Es instrument-agnostic y polifónico (toca acordes), pero su documentación dice
  "works best on one instrument at a time".
- Si le pasas UNA pieza de piano, guitarra o voz sola → muy buena precisión.
- Si le pasas una CANCIÓN COMPLETA (batería + bajo + piano + voz) → saca TODAS las notas
  MEZCLADAS en UNA sola pista MIDI. No distingue "pista de piano" de "pista de bajo".

Para multi-pista real haría falta una fase extra:
1. **Source separation** (Demucs de Meta, o Spleeter) → separa stems
   (drums / bass / other / vocals).
2. Basic Pitch **por stem** → un track MIDI por instrumento.
Esto es mucho más pesado (PyTorch, lento en CPU, otra instalación grande) y frágil.
Queda como **fase 3 opcional**, no para la v1.

---

## Pendiente / próximos pasos (sujetos a tu elección)

A. Pulir v1  [HECHO]
   - [x] Suite pytest repetible (9 passed) en backend/tests/.
   - [x] Deep-link "Abrir en MidiMate" (copia .mid a MidiMate/midiforja_inbox).
   - [x] Manejo de errores amigable (archivo sin audio, formato raro).
   - [ ] README con capturas / demo (en curso).

B. OMR (fase 2) — partitura → MIDI  [HECHO]
   - Audiveris 5.11 instalado y auto-detectado; endpoint `/api/transcribe-sheet` operativo.

C. Multi-instrumento (fase 3)
   - Demucs + basic-pitch por stem → MIDI multi-pista.

D. Publicación  [EN CURSO]
   - [x] Repo local listo (creds/IP escaneados, .venv/node_modules ignorados).
   - [ ] Crear repo en GitHub (zabat-code/Midiforja) y pushear.
   - [ ] HARD-RELOAD note para quien pruebe el frontend.

---

## Cómo correr (dev)

Backend: `cd Midiforja && .venv\Scripts\activate && pip install -r backend\requirements.txt && python backend\server.py`
Frontend: `cd Midiforja\frontend && npm install && npx vite --port 5174`
Abrir: http://127.0.0.1:5174/  · API: http://127.0.0.1:8000/

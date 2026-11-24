# Midiforja — Plan (actualizado al día)

> **Estado 2026-11-23 (v0.5-study):** Midiforja funciona como herramienta
> independiente: audio/video, partitura o `.mid` → análisis musical → pack de
> estudio JSON guardado en SQLite. MidiMate **no se modifica**: sigue consumiendo
> el `.mid` de siempre por drag & drop. Verificado con `36 passed` (pytest) y
> `node --check` en el frontend. Sin errores detectados en las pruebas.
>
> **Novedades de esta iteración:**
> - `midi_reader.py`: lector SMF propio (sin `pretty_midi`/`mido`).
> - `music_analysis.py`: BPM, tonalidad, acordes, ritmo, densidad y dificultad.
> - `study_db.py`: SQLite local con historial, filtros, descarga y borrado.
> - `ws_server.py`: secuencias por conexión, `event_id`, dedup y heartbeat;
>   acepta `event/data` y `type/payload`, emite ambos alias.
> - `server.py`: `asyncio.to_thread`, rate limit, `/files/{id}`, CORS para
>   `8765`/`null`, endpoints `/api/analyze-midi`, `/api/analyses`, `/api/stats`
>   y descarga del pack.
> - Frontend: pestaña “Analizar MIDI”, resumen visual y biblioteca con
>   búsqueda/filtros/estadísticas (ES/EN).
>
> **Pendiente de publicación:** commit en `feature/api-ws-integration` y push
> (los commits `e98ae10` y `f0eb75a` todavía no están en el remoto).

App para convertir audio/video en MIDI, y partituras en imagen/PDF.
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

## Mejoras recientes (v0.3)

Hecho / verificado:
- **Nombre del .mid = nombre del archivo fuente**: en `/api/transcribe` y
  `/api/transcribe-sheet` el `Content-Disposition` y el header `X-Filename` usan
  el nombre del archivo subido (sanitizado, p.ej. `mi_piano.wav -> mi_piano.mid`).
- **Calidad/ritmo post-creación** (`backend/quality_check.py`): detecta el beat
  grid (librosa), permite **cuantizar** el ritmo a la grilla, y devuelve una
  métrica de fidelidad de tiempo/ritmo (`mir_eval` f-measure + desviación mediana)
  en el header `X-Quality`. El frontend la muestra ("Calidad de ritmo: 94%").
- **Opciones en el frontend**: checkbox "Eliminar la voz" y "Ajustar ritmo a la
  grilla (cuantizar)" en la pestaña Audio/Video; test `backend/test_quality.py` OK.

Pendiente / condicionado:
- **Omitir la voz (Meta 1)**: ✅ OPERATIVO. `backend/vocal_separation.py` usa **Demucs**
  (PyTorch CPU instalado y verificado: produce el stem `no_vocals` correctamente) para
  separar y descartar el stem de vocals ANTES de Basic Pitch. La primera ejecución descarga
  el modelo `htdemucs` (~80 MB) y en CPU tarda (unos 70 s en un corte corto).
- **Integrar Audiveris (Meta 2)**: `server.py` YA prefiere el binario vendoreado
  (`audiveris-master/app/build/install/...`) si existe; `scripts/build_audiveris.bat`
  prepara el build. **BLOQUEADO**: la rama `master` de Audiveris exige **Java 25**
  (`theMinJavaVersion = 25`) y este equipo tiene JDK 17, y no hay Gradle ni wrapper.
  Por ahora se usa el Audiveris 5.11 instalado (auto-detect) como fallback.



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
   - [x] Repo creado en GitHub (Zabat-code/Midiforja); rama de trabajo
     `feature/api-ws-integration`.
   - [x] Commit de v0.5-study pusheado: `75cfae4` en `feature/api-ws-integration`.
   - [x] Token del remote limpiado; copias locales borradas. Si se usaron tokens
     para API/push, revocarlos en GitHub Settings.
   - [ ] HARD-RELOAD note para quien pruebe el frontend.

E. Análisis y pack de estudio (v0.5)  [HECHO]
   - [x] Lector SMF propio y análisis desde bytes `.mid` (audio, OMR y MIDI).
   - [x] Pack de estudio JSON + base SQLite con búsqueda y descarga.
   - [x] E2E real de transcripción en Linux: Basic Pitch 0.4.0 con Python 3.11,
     NumPy 1.26.4 y setuptools<81. `test_e2e.py` OK (8/8 notas y cross-check con
     el parser de MidiMate: 480 ticks/beat); 25 s del `.opus` de prueba → 131
     notas, A major, 142,9 BPM, `.mid` + pack en SQLite.
     El paquete PyPI es el código oficial de Spotify (Apache-2.0), multiplataforma.
   - [x] UI: pestaña de análisis, resumen y biblioteca (ES/EN).
   - [x] Suite ampliada: 36 tests, 0 errores detectados.
   - [ ] E2E real de transcripción con Basic Pitch instalado en el venv (el
     Python del sistema no tiene `basic_pitch`; no se pudo ejecutar aquí).

---

## Cómo correr (dev)

Backend: `cd Midiforja && .venv\Scripts\activate && pip install -r backend\requirements.txt && python backend\server.py`
Frontend: `cd Midiforja\frontend && npm install && npx vite --port 5174`
Abrir: http://127.0.0.1:5174/  · API: http://127.0.0.1:8000/

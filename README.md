# Midiforja

> Audio, video, partituras o `.mid` → análisis musical → **pack de estudio** en JSON
> y una base de datos local SQLite. El `.mid` resultante sirve como puente manual a
> [MidiMate](https://github.com/Zabat-code) y a cualquier DAW.

## Stack

- **Backend** (Python 3.11+): FastAPI, Spotify **Basic Pitch** (Apache-2.0) para
  transcripción de audio, `ffmpeg` para vídeo/Opus, y un escritor/lector de Standard
  MIDI File propios (`midiwriter.py`, `midi_reader.py`) sin dependencias pesadas.
- **Análisis** (`music_analysis.py`): notas normalizadas, acordes, tonalidad, ritmo,
  densidad y dificultad. No necesita `pretty_midi`/`mido`.
- **Base de datos** (`study_db.py`): SQLite local con historial, búsqueda por
  archivo/tonalidad/acorde, filtros por tipo y dificultad, y exportación del pack.
- **Frontend** (Vite + vanilla JS): tres pestañas — Audio/Video, Partitura y
  Analizar MIDI — más biblioteca de estudio, con i18n **ES/EN**.

## Funciones destacadas

- `mp3/opus/wav/… → .mid` con nombre derivado del archivo fuente.
- Opciones: quitar voz (Demucs) y cuantizar al beat detectado.
- Calidad de ritmo comparando onsets de audio vs MIDI (`mir_eval`, opcional).
- Partitura (imagen/PDF) → MusicXML vía Audiveris → `.mid`, con tempo y
  `divisions` corregidos.
- **Analizar un `.mid` existente** y obtener:
  - `notes`: tiempo, duración, pitch, velocidad y nombre de nota.
  - `analysis.key`: tonalidad, modo, confianza y escala.
  - `analysis.chords`: acordes con root, calidad y frecuencia.
  - `analysis.rhythm`: BPM, densidad, sincopación e histograma de duraciones.
  - `analysis.difficulty`: puntuación 0–100, nivel 1–4 y rango/polifonía.
- Guardado automático del pack en SQLite al transcribir audio, partitura o analizar
  un MIDI; descarga como `*.study-pack.json`.
- Servidor con rate limit, heartbeat WS, secuencias por cliente y trabajo pesado
  fuera del event loop (`asyncio.to_thread`).

## Requisitos

- Python **3.11** para la transcripción en Linux (usa `backend/.venv` en Windows o
  un venv en la raíz). `basic-pitch==0.4.0` fija `tensorflow<2.15.1`, que no tiene
  build para Python 3.12+; el resto del backend sí funciona en 3.12.
- `setuptools<81` en el venv: Basic Pitch usa `pkg_resources`, eliminado en 84.
- Node 18+ y npm para Vite.
- `ffmpeg` en el PATH (decodea Opus/OGG/MP4).
- Opcionales: `basic-pitch` (transcripción), `mir_eval` (calidad), Demucs+torch
  (quitar voz) y Audiveris (OMR).

## Puertos

- Backend: `http://127.0.0.1:8000`
- Frontend dev: `http://127.0.0.1:5174`

## Cómo correr (dev)

```bat
cd <repo>\Midiforja
.venv\Scripts\activate
pip install -r backend\requirements.txt
python backend\server.py
```

En otra terminal:

```bat
cd <repo>\Midiforja\frontend
npm install
npx vite --port 5174
```

Abre `http://127.0.0.1:5174/`. También existen `run_backend.bat` y `run_frontend.bat`.

## Flujo recomendado

1. **Audio/video** → “Transcribir a MIDI”: descarga el `.mid` y guarda su análisis.
2. **Partitura** → “Convertir partitura a MIDI” (requiere Audiveris).
3. **Analizar MIDI** → suelta cualquier `.mid` (incluso generado fuera de Midiforja).
4. En la **Biblioteca de estudio**, filtra, abre un análisis o descarga el pack JSON.
5. Carga el `.mid` en MidiMate por drag & drop. Midiforja **no modifica** MidiMate.

## API principal

| Método | Ruta | Uso |
|---|---|---|
| `POST` | `/api/transcribe` | audio/video → `.mid` + análisis |
| `POST` | `/api/transcribe-sheet` | imagen/PDF → `.mid` + análisis (Audiveris) |
| `POST` | `/api/analyze-midi` | `.mid` → pack de estudio |
| `GET` | `/api/analyses` | listado con `search`, `key`, `kind`, `min_difficulty`, `max_difficulty` |
| `GET` | `/api/analyses/{id}` | pack completo |
| `GET` | `/api/study-pack/{id}` | descarga del JSON |
| `GET` | `/api/analyses/{id}/midi` | descarga del `.mid` guardado |
| `DELETE` | `/api/analyses/{id}` | borrar análisis |
| `GET` | `/api/stats` | estadísticas de la base |
| `GET` | `/files/{id}` | `.mid` stashado (acepta con/sin `.mid`) |
| `GET` | `/api/midimate/*` | API/WS opcional para MidiMate |

Ejemplo:

```bash
# Analizar un MIDI existente (el pack se guarda en SQLite):
curl -F "file=@mi_piano.mid" http://127.0.0.1:8000/api/analyze-midi

# Transcribir audio: la respuesta ES el .mid y también guarda su pack:
curl -F "file=@mi_piano.mp3" -o salida.mid http://127.0.0.1:8000/api/transcribe
```

La respuesta de transcripción incluye `X-Analysis-Id`, `X-Note-Count` y
`X-Midi-Url`; el pack se consulta después en `/api/study-pack/{id}`.

## Configuración

Copia `backend/.env.example` y ajusta:

- `MIDIFORJA_DB_PATH`: ruta del SQLite (por defecto `backend/data/midiforja.db`).
- `MIDIFORJA_RATE_LIMIT_MAX`: peticiones `/api/*` por minuto por IP (default 30).
- `MIDIFORJA_MIDIMATE_DIR` / `MIDIFORJA_MIDIMATE_URL`: sólo para el botón opcional
  “Abrir en MidiMate”.
- `MIDIFORJA_AUDIVERIS_BIN` / `MIDIFORJA_OMR_TIMEOUT`: OMR.

## Pruebas

```bash
cd backend
python -m pytest -q
```

La suite cubre escritor/lector MIDI, `musicxml2midi`, análisis musical, base SQLite,
endpoints y el protocolo WS. Sin errores detectados en las pruebas. La transcripción
real con Basic Pitch se valida aparte en `test_e2e.py` (requiere el modelo instalado).

E2E real verificado en Linux (Python 3.11 + `basic-pitch==0.4.0`, TensorFlow 2.14,
NumPy 1.26.4): `test_e2e.py` → 8/8 notas y cross-check con el parser de MidiMate
(480 ticks/beat), y 25 s del `.opus` de prueba del repo → 131 notas, A major,
142,9 BPM, con el `.mid` y su pack guardados en SQLite. Basic Pitch
es el paquete oficial multiplataforma de Spotify (Apache-2.0); no hace falta clonar
su código ni buscar un sustituto para Linux.

## Estructura

```
backend/
  server.py            # FastAPI, endpoints y middleware
  midiwriter.py        # SMF writer
  midi_reader.py       # SMF reader (para analizar .mid)
  musicxml2midi.py     # MusicXML -> notas/MIDI
  music_analysis.py    # pack de estudio
  study_db.py          # SQLite local
  quality_check.py     # beat grid, cuantización, fidelity
  vocal_separation.py  # Demucs opcional
  midimate_router.py   # REST + WS opcional
  ws_server.py         # hub WS con secuencias por cliente
  test_*.py            # suite pytest
frontend/
  index.html
  src/main.js
  src/i18n.js
  src/style.css
```

## Límites conocidos

- Basic Pitch funciona mejor con **un instrumento a la vez**; una canción completa
  mezcla notas de varios instrumentos.
- Audiveris es externo y su instalación/compilación depende de Java.
- Sin GPU, la transcripción puede tardar varios minutos.
- Los packs se guardan en local; no hay sincronización entre equipos.

## Licencia

Código de Midiforja: MIT. Basic Pitch (Spotify): Apache-2.0. Audiveris: Apache-2.0.

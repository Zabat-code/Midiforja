"""
midi_reader.py - Lector mínimo de Standard MIDI File (SMF), sin dependencias.

Complemento de midiwriter.py: permite a Midiforja ANALIZAR un .mid existente
sin arrastrar pretty_midi/mido. Lee notas (con su canal), cambios de tempo y
convierte ticks a segundos respetando el mapa de tempo.

Soporta formatos SMF 0/1/2 con divisiones positivas (ticks por beat).
"""

import struct


def _vlq(data: bytes, pos: int):
    """Lee un variable-length quantity y devuelve (valor, nueva_posición)."""
    value = 0
    while True:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos


def parse_midi(data: bytes) -> dict:
    """Parsea un SMF y devuelve notas en ticks absolutas y cambios de tempo."""
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("No es un Standard MIDI File (falta MThd).")
    header_len = struct.unpack(">I", data[4:8])[0]
    fmt, ntracks, division = struct.unpack(">HHH", data[8:14])
    if division == 0:
        raise ValueError("El MIDI usa divisiones SMPTE, no soportadas.")
    pos = 8 + header_len

    notes = []            # (start_tick, end_tick, pitch, velocity)
    tempo_changes = []    # (tick, microseconds_por_beat)
    active = {}           # (canal, pitch) -> [(tick_inicial, velocity), ...]

    for _ in range(ntracks):
        if data[pos:pos + 4] != b"MTrk":
            raise ValueError("Pista MIDI inválida (falta MTrk).")
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        pos += 8
        end = pos + length
        tick = 0
        running = None

        while pos < end:
            delta, pos = _vlq(data, pos)
            tick += delta
            byte = data[pos]
            if byte & 0x80:
                status = byte
                pos += 1
                if status < 0xF0:
                    running = status
            else:
                status = running
                if status is None:
                    raise ValueError("Evento MIDI sin status y sin running status.")

            if status == 0xFF:
                meta = data[pos]
                pos += 1
                size, pos = _vlq(data, pos)
                payload = data[pos:pos + size]
                pos += size
                if meta == 0x51 and len(payload) >= 3:
                    tempo_changes.append((tick, int.from_bytes(payload[:3], "big")))
                continue

            if 0x80 <= status <= 0xEF:
                kind = status & 0xF0
                channel = status & 0x0F
                size = 1 if kind in (0xC0, 0xD0) else 2
                d1 = data[pos]
                d2 = data[pos + 1] if size == 2 else 0
                pos += size
                key = (channel, d1)
                if kind == 0x90 and d2 > 0:
                    active.setdefault(key, []).append((tick, d2))
                elif kind == 0x80 or (kind == 0x90 and d2 == 0):
                    starts = active.get(key)
                    if starts:
                        start, velocity = starts.pop(0)
                        notes.append((start, tick, d1, velocity))
            # 0xF0/0xF7 (sysex): se ignora, sólo importan los bytes de longitud.
            elif status in (0xF0, 0xF7):
                _, pos = _vlq(data, pos)

    notes.sort(key=lambda n: (n[0], n[2]))
    tempo_changes.sort()
    return {
        "format": fmt,
        "ticks_per_beat": division,
        "notes": notes,
        "tempo_changes": tempo_changes,
    }


def to_seconds(parsed: dict):
    """Convierte las notas del parseo a (start_s, end_s, pitch, velocity) y BPM."""
    division = parsed.get("ticks_per_beat") or 480
    changes = parsed.get("tempo_changes") or [(0, 500000)]

    def tick_to_sec(tick: int) -> float:
        seconds = 0.0
        prev_tick = 0
        micros = 500000
        for change_tick, change_micros in changes:
            if change_tick > tick:
                break
            seconds += (change_tick - prev_tick) * micros / (1_000_000.0 * division)
            prev_tick = change_tick
            micros = change_micros
        seconds += (tick - prev_tick) * micros / (1_000_000.0 * division)
        return seconds

    notes = [
        (round(tick_to_sec(start), 4), round(tick_to_sec(end), 4), pitch, velocity)
        for start, end, pitch, velocity in parsed["notes"]
    ]
    bpm = 60_000_000.0 / changes[0][1] if changes else 120.0
    return notes, bpm


def read_midi(data: bytes):
    """Atajo: bytes SMF -> (notes_en_segundos, bpm)."""
    return to_seconds(parse_midi(data))

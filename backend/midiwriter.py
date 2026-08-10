"""
midiwriter.py - Minimal Standard MIDI File (SMF) writer.

Emits a Type 1 file with:
  * Track 0: tempo meta event (so playback speed is correct).
  * Track 1: note_on / note_off events placed at absolute tick positions
    derived from seconds, using division = ticksPerBeat and a fixed tempo.

This format is parsed correctly by MidiMate's src/midi.js (MThd/MTrk), which
reads ticksPerBeat + tempo meta and converts ticks -> seconds.
"""

import struct


def _vlq(value: int) -> bytes:
    """Variable-length quantity encoding (MIDI delta times)."""
    if value < 0:
        value = 0
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(out)


def _u32(v: int) -> bytes:
    return struct.pack(">I", v & 0xFFFFFFFF)


def _u16(v: int) -> bytes:
    return struct.pack(">H", v & 0xFFFF)


def _u24(v: int) -> bytes:
    return bytes([(v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])


def write_midi(notes, ticks_per_beat: int = 480, bpm: int = 120, channel: int = 0) -> bytes:
    """
    notes: list of (start_sec, end_sec, pitch, velocity_0_127)
    Returns MIDI file bytes.
    """
    # Tempo: microseconds per beat.
    mpb = int(60_000_000 / bpm)
    secs_per_beat = 60.0 / bpm
    ticks_per_sec = ticks_per_beat / secs_per_beat  # = ticks_per_beat * bpm / 60

    # ---- Track 0: tempo + end of track ----
    t0_events = bytearray()
    # delta 0, meta tempo
    t0_events += b"\x00\xff\x51\x03" + _u24(mpb)
    # delta 0, end of track
    t0_events += b"\x00\xff\x2f\x00"
    track0 = b"MTrk" + _u32(len(t0_events)) + bytes(t0_events)

    # ---- Track 1: notes ----
    # Build a sorted list of (tick, is_on, pitch, velocity)
    events = []
    for (start_sec, end_sec, pitch, vel) in notes:
        on_tick = int(round(start_sec * ticks_per_sec))
        off_tick = int(round(end_sec * ticks_per_sec))
        if off_tick <= on_tick:
            off_tick = on_tick + 1
        events.append((on_tick, True, int(pitch), int(vel)))
        events.append((off_tick, False, int(pitch), 0))
    events.sort(key=lambda e: (e[0], 0 if e[1] else 1))

    t1 = bytearray()
    last_tick = 0
    for (tick, is_on, pitch, vel) in events:
        delta = tick - last_tick
        last_tick = tick
        t1 += _vlq(delta)
        if is_on:
            t1 += bytes([0x90 | (channel & 0x0F), pitch & 0x7F, max(1, min(127, vel))])
        else:
            t1 += bytes([0x80 | (channel & 0x0F), pitch & 0x7F, 0])
    # end of track
    t1 += b"\x00\xff\x2f\x00"
    track1 = b"MTrk" + _u32(len(t1)) + bytes(t1)

    # ---- Header ----
    header = b"MThd" + _u32(6) + _u16(1) + _u16(2) + _u16(ticks_per_beat)

    return header + track0 + track1

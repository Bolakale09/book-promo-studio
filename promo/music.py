"""Built-in background music: original tracks made by code (no downloads, no licences, no copyright claims).

Each style is a 16-bar loop of a few simple instruments (piano, pluck, pad, bells, bass, soft drums) played through a
room reverb. The reverb wraps around the end, so the loop has no click and no gap, and short videos simply use its
first seconds. Tracks are made once and cached; the render mixes them under the narrator (they duck when it speaks).
"""
import wave
from pathlib import Path

import numpy as np

from . import config, ffmpeg_utils as ff

SR = 44100
DIR = config.DATA / "musicgen"
VERSION = 2   # bump to remake cached tracks after changing a recipe
BARS = 16

STYLES = {
    "warm-piano": {"label": "Warm piano", "mood": "soft, hopeful, personal", "genres": ["fiction", "gift", "poetry"],
                   "bpm": 72, "seed": 11},
    "dark-cinematic": {"label": "Dark cinematic", "mood": "tense, slow-building, mysterious", "genres": ["fiction"],
                       "bpm": 64, "seed": 23},
    "uplift": {"label": "Uplift", "mood": "bright, motivating, forward", "genres": ["self-help"],
               "bpm": 104, "seed": 37},
    "calm-ambient": {"label": "Calm ambient", "mood": "quiet, spacious, soothing", "genres": ["poetry", "medical"],
                     "bpm": 56, "seed": 41},
    "clean-tech": {"label": "Clean tech", "mood": "focused, precise, modern", "genres": ["engineering", "medical"],
                   "bpm": 108, "seed": 53},
    "playful": {"label": "Playful", "mood": "bouncy, cheerful, curious", "genres": ["children"],
                "bpm": 116, "seed": 67},
    "lofi-study": {"label": "Lo-fi study", "mood": "cosy, mellow, bookish", "genres": ["fiction", "self-help", "gift"],
                   "bpm": 76, "seed": 71},
}


def suggested(genre: str) -> str:
    return next((k for k, v in STYLES.items() if v["genres"][0] == genre), "warm-piano")


# ---- instruments (each returns a mono float array: the note plus its ring-out) -----------------------------

def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _t(n: int) -> np.ndarray:
    return np.arange(n) / SR


def _release(t: np.ndarray, hold: float, tail: float = 0.09) -> np.ndarray:
    return np.clip((hold + tail - t) / tail, 0, 1)


def epiano(f: float, hold: float, vel: float = 1.0) -> np.ndarray:
    n = int((hold + 1.6) * SR)
    t = _t(n)
    sig = (np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.5)
           + 0.16 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t / 0.25)
           + 0.07 * np.sin(2 * np.pi * 7.02 * f * t) * np.exp(-t / 0.07))
    sig *= np.exp(-t / (1.5 if f < 400 else 1.0)) * (1 - np.exp(-t / 0.004)) * (1 + 0.05 * np.sin(2 * np.pi * 4.3 * t))
    return np.tanh(sig * 0.9) * _release(t, hold, 0.25) * vel * 0.5


def pluck(f: float, hold: float, vel: float = 1.0) -> np.ndarray:
    n = int((hold + 1.2) * SR)
    t = _t(n)
    sig = sum(np.sin(2 * np.pi * f * h * t) / h ** 1.25 * np.exp(-t * (2.2 + 1.8 * h)) for h in range(1, 9))
    return sig * (1 - np.exp(-t / 0.002)) * _release(t, hold + 0.6, 0.2) * vel * 0.55


def marimba(f: float, hold: float, vel: float = 1.0) -> np.ndarray:
    n = int(0.9 * SR)
    t = _t(n)
    sig = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.22) + 0.35 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t / 0.06)
    return sig * (1 - np.exp(-t / 0.001)) * vel * 0.6


def bell(f: float, hold: float, vel: float = 1.0) -> np.ndarray:
    n = int((hold + 2.6) * SR)
    t = _t(n)
    sig = (np.sin(2 * np.pi * f * t) * np.exp(-t / 1.4) + 0.4 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t / 0.7)
           + 0.15 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t / 0.3))
    return sig * (1 - np.exp(-t / 0.003)) * vel * 0.4


def pad(freqs: list, hold: float, vel: float = 1.0, dark: bool = False) -> np.ndarray:
    tail = 1.2
    n = int((hold + tail) * SR)
    t = _t(n)
    rng = np.random.default_rng(int(sum(freqs)))
    sig = np.zeros(n)
    top = 4 if dark else 6
    for f in freqs:
        for det in (-0.0055, 0.0, 0.0055):
            ph = rng.uniform(0, 6.28)
            for h in range(1, top + 1):
                sig += np.sin(2 * np.pi * f * (1 + det) * h * t + ph * h) / h ** 1.5
    env = np.minimum(1, t / 0.7) * np.clip((hold + tail - t) / tail, 0, 1)
    return sig * env * vel * 0.08 / max(1, len(freqs) / 3)


def bass(f: float, hold: float, vel: float = 1.0) -> np.ndarray:
    n = int((hold + 0.3) * SR)
    t = _t(n)
    sig = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.2)
    return sig * (1 - np.exp(-t / 0.01)) * np.exp(-t / 0.9) * _release(t, hold, 0.15) * vel * 0.6


def drone(f: float, hold: float, vel: float = 1.0) -> np.ndarray:
    n = int((hold + 1.0) * SR)
    t = _t(n)
    sig = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t + np.sin(2 * np.pi * 0.2 * t))
    return sig * np.minimum(1, t / 1.0) * np.clip((hold + 1.0 - t) / 1.0, 0, 1) * vel * 0.32


def kick(vel: float = 1.0, deep: bool = False) -> np.ndarray:
    t = _t(int(0.45 * SR))
    freq = 50 + (110 if not deep else 70) * np.exp(-t / 0.035)
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / 0.13) * vel * 0.9


def _noise(seed: int, n: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n)


def hat(vel: float = 1.0, open_: bool = False, seed: int = 1) -> np.ndarray:
    n = int((0.22 if open_ else 0.06) * SR)
    t = _t(n)
    x = np.diff(_noise(seed, n + 1))
    return x * np.exp(-t / (0.07 if open_ else 0.018)) * vel * 0.16


def snare(vel: float = 1.0, seed: int = 2, soft: bool = False) -> np.ndarray:
    n = int(0.22 * SR)
    t = _t(n)
    body = np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.05)
    hiss = np.diff(_noise(seed, n + 1)) * np.exp(-t / (0.06 if soft else 0.09))
    return (0.4 * body + 0.55 * hiss) * vel * 0.55


def shaker(vel: float = 1.0, seed: int = 3) -> np.ndarray:
    n = int(0.1 * SR)
    t = _t(n)
    return np.diff(_noise(seed, n + 1)) * np.exp(-t / 0.03) * np.minimum(1, t / 0.012) * vel * 0.13


def vinyl(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n) * 0.0016
    clicks = rng.random(n) < 2.2 / SR * 1.0
    x[clicks] += rng.standard_normal(int(clicks.sum())) * 0.03
    return x


# ---- mixing ------------------------------------------------------------------------------------

def _chord(root: int, quality: str, center: int = 60) -> list:
    iv = {"maj": (0, 4, 7), "min": (0, 3, 7), "maj7": (0, 4, 7, 11), "min7": (0, 3, 7, 10), "dom7": (0, 4, 7, 10),
          "add9": (0, 4, 7, 14), "min9": (0, 3, 7, 10, 14)}[quality]
    notes = []
    for i in iv:
        m = root + i
        while m >= center + 7:
            m -= 12
        while m < center - 5:
            m += 12
        notes.append(m)
    return sorted(notes)


class Mixer:
    def __init__(self, bpm: float, seed: int):
        self.beat = int(round(60 / bpm * SR))
        self.n = BARS * 4 * self.beat
        self.dry = np.zeros((2, self.n), np.float32)
        self.wet = np.zeros((2, self.n), np.float32)
        self.rng = np.random.default_rng(seed)
        self.cache: dict = {}

    def sec(self, bar: float, beat: float = 0.0) -> float:
        return (bar * 4 + beat) * self.beat / SR

    def dur(self, beats: float) -> float:
        return beats * self.beat / SR

    def put(self, sig: np.ndarray, at: float, pan: float = 0.0, dry: float = 1.0, wet: float = 0.0) -> None:
        """Add a sound at `at` seconds; anything past the end wraps to the start so the loop is seamless."""
        start = int(at * SR) % self.n
        sig = sig.astype(np.float32)
        gl, gr = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        pos = 0
        while pos < len(sig):
            take = min(len(sig) - pos, self.n - start)
            seg = sig[pos:pos + take]
            for buf, amt in ((self.dry, dry), (self.wet, wet)):
                if amt:
                    buf[0, start:start + take] += seg * gl * amt
                    buf[1, start:start + take] += seg * gr * amt
            pos += take
            start = 0

    def voice(self, fn, key, *args, **kw) -> np.ndarray:
        k = (fn.__name__, key, tuple(args), tuple(sorted(kw.items())))
        if k not in self.cache:
            self.cache[k] = fn(*args, **kw)
        return self.cache[k]

    def finish(self, reverb: float, size: float = 1.9, tone: float = 0.6, extra: np.ndarray | None = None) -> np.ndarray:
        """Room reverb (wraps around), gentle level and limiter -> stereo int16."""
        L = int(size * SR)
        t = _t(L)
        out = self.dry.copy()
        if reverb > 0:
            wet = np.zeros_like(self.dry)
            for ch in range(2):
                ir = _noise(900 + ch, L) * np.exp(-t / (size / 5.5))
                k = max(2, int(14 * (1 - tone)))            # duller tail when `tone` is low
                ir = np.convolve(ir, np.ones(k) / k, "same")
                ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))
                ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
                wet[ch] = np.fft.irfft(np.fft.rfft(self.wet[ch] + 0.35 * self.dry[ch]) * np.fft.rfft(ir, self.n), self.n)
            out += wet * reverb
        if extra is not None:
            out += extra[None, :]
        out -= out.mean(axis=1, keepdims=True)
        rms = np.sqrt(np.mean(out ** 2))
        out *= 0.115 / max(rms, 1e-6)
        out = np.tanh(out * 1.15) / 1.15
        peak = np.abs(out).max()
        if peak > 0.85:
            out *= 0.85 / peak
        return (out.T * 32767).astype(np.int16)


def _melody(m: Mixer, chords: list, scale: list, bars: range, fn, lo: int, hi: int, density: float = 0.55,
            wet: float = 0.6, pan: float = 0.25) -> None:
    """A sparse tune that leans on the chord tones and moves mostly by step."""
    rng = m.rng
    prev = None
    for bar in bars:
        tones = {n % 12 for n in chords[bar % 4]}
        pool = [n for n in range(lo, hi + 1) if n % 12 in {s % 12 for s in scale}]
        beat = 0.0
        while beat < 4:
            if rng.random() < density:
                near = [n for n in pool if prev is None or abs(n - prev) <= 4] or pool
                strong = [n for n in near if n % 12 in tones]
                note = int(rng.choice(strong if strong and (beat in (0.0, 2.0) or rng.random() < 0.6) else near))
                hold = float(rng.choice([1.0, 1.5, 2.0]))
                m.put(m.voice(fn, note, _hz(note), m.dur(hold)), m.sec(bar, beat), pan * rng.choice([-1, 1]),
                      dry=0.55, wet=wet)
                prev = note
                beat += float(rng.choice([1.0, 1.5, 2.0]))
            else:
                beat += 1.0


def _pads(m: Mixer, chords: list, from_bar: int = 0, vel: float = 1.0, dark: bool = False, shift: int = 0) -> None:
    for bar in range(from_bar, BARS):
        ch = [n + shift for n in chords[bar % 4]]
        m.put(m.voice(pad, (bar % 4, shift, dark), tuple(_hz(n) for n in ch), m.dur(4), vel, dark=dark),
              m.sec(bar), 0.0, dry=0.8, wet=0.7)


def _arp(m: Mixer, chords: list, fn, pattern: list, step: float, from_bar: int = 0, vel: float = 0.7,
         lift: int = 0, wet: float = 0.5, swing: float = 0.0) -> None:
    for bar in range(from_bar, BARS):
        ch = chords[bar % 4]
        for i, idx in enumerate(pattern):
            if idx is None:
                continue
            note = ch[idx % len(ch)] + 12 * (idx // len(ch)) + lift
            beat = i * step + (swing * step if i % 2 else 0)
            v = vel * (1.0 if (i * step) % 1 == 0 else 0.8) * (0.9 + 0.2 * m.rng.random())
            m.put(m.voice(fn, note, _hz(note), m.dur(step * 2.2), 1.0), m.sec(bar, beat), 0.15 * (-1) ** i,
                  dry=v, wet=wet * v)


def _bass_line(m: Mixer, roots: list, beats: list, from_bar: int = 0, vel: float = 0.8, octave: int = 36) -> None:
    for bar in range(from_bar, BARS):
        r = roots[bar % 4]
        for b, hold, off in beats:
            note = octave + (r % 12) + off
            m.put(m.voice(bass, note, _hz(note), m.dur(hold)), m.sec(bar, b), 0.0, dry=vel, wet=0.05)


def _drums(m: Mixer, from_bar: int, kicks: list, snares: list, hats: list, shake: list = (), swing: float = 0.0,
           vel: float = 0.7, soft: bool = True, deep: bool = False) -> None:
    for bar in range(from_bar, BARS):
        for b in kicks:
            m.put(m.voice(kick, deep, 1.0, deep), m.sec(bar, b), 0.0, dry=vel, wet=0.05)
        for b in snares:
            m.put(m.voice(snare, soft, 1.0, 2, soft=soft), m.sec(bar, b), 0.05, dry=vel * 0.8, wet=0.25)
        for b in hats:
            off = swing if (b * 2) % 2 == 1 else 0.0
            m.put(m.voice(hat, int(b * 4), 1.0, False, int(b * 8) + 5), m.sec(bar, b + off), 0.25 * (-1) ** int(b * 2),
                  dry=vel * (0.55 if b % 1 else 0.8), wet=0.06)
        for b in shake:
            m.put(m.voice(shaker, int(b * 4), 1.0, int(b * 8) + 9), m.sec(bar, b), -0.3, dry=vel * 0.8, wet=0.05)


def _key(root: int, quals: list, center: int = 60) -> tuple[list, list]:
    """(chord tones per bar, chord roots) for a 4-chord progression given as (semitones from root, quality)."""
    chords = [_chord(root + s, q, center) for s, q in quals]
    return chords, [root + s for s, _ in quals]


MAJ_PENT = [0, 2, 4, 7, 9]
MIN_PENT = [0, 3, 5, 7, 10]


def _build(style: str) -> np.ndarray:
    cfg = STYLES[style]
    m = Mixer(cfg["bpm"], cfg["seed"])
    if style == "warm-piano":
        chords, roots = _key(57, [(0, "min"), (-4, "maj"), (3, "maj"), (10, "maj")], 60)
        _pads(m, chords, 0, 0.9)
        _arp(m, chords, epiano, [0, 1, 2, 1, 3 - 0, 2, 1, 2], 0.5, 0, 0.55, 0, 0.55)
        _bass_line(m, roots, [(0, 3.6, 0), (2, 1.8, 7)], 4, 0.55)
        _melody(m, chords, [57 + s for s in MIN_PENT], range(8, 16), bell, 76, 88, 0.5, 0.9)
        return m.finish(0.42, 2.2, 0.5)
    if style == "dark-cinematic":
        chords, roots = _key(50, [(0, "min"), (-4, "maj"), (-9 + 12, "min"), (-5 + 12, "maj")], 55)
        _pads(m, chords, 0, 1.1, dark=True, shift=-12)
        for bar in range(BARS):
            n = 26 if bar % 4 < 2 else 24
            m.put(m.voice(drone, n, _hz(n), m.dur(4)), m.sec(bar), 0, dry=0.9, wet=0.3)
        for bar in range(4, BARS):
            for b in (0, 2.5) if bar % 2 else (0, 2):
                m.put(m.voice(kick, True, 0.8, True), m.sec(bar, b), 0, dry=0.55, wet=0.4)
        _arp(m, chords, bell, [None, None, 2, None, None, None, 3, None], 0.5, 8, 0.45, 12, 0.9)
        _melody(m, chords, [50 + s for s in MIN_PENT], range(10, 16), pluck, 74, 86, 0.35, 0.95, 0.5)
        return m.finish(0.6, 3.0, 0.35)
    if style == "uplift":
        chords, roots = _key(55, [(0, "maj"), (7, "maj"), (9, "min"), (5, "maj")], 62)
        chords = [[n if n < 74 else n - 12 for n in c] for c in chords]
        _pads(m, chords, 0, 0.8)
        _arp(m, chords, pluck, [0, 2, 1, 2, 0, 2, 1, 2], 0.5, 0, 0.6, 0, 0.35)
        _bass_line(m, roots, [(0, 0.9, 0), (1.5, 0.9, 0), (2, 0.9, 0), (3.5, 0.5, 7)], 2, 0.7)
        _drums(m, 4, [0, 2], [1, 3], [0.5, 1.5, 2.5, 3.5], [1, 3], 0.0, 0.55)
        _melody(m, chords, [55 + s for s in MAJ_PENT], range(8, 16), bell, 79, 91, 0.6, 0.6)
        return m.finish(0.28, 1.5, 0.7)
    if style == "calm-ambient":
        chords, roots = _key(53, [(0, "maj7"), (-1, "min7"), (-5, "maj7"), (-5 + 7, "add9")], 60)
        chords = [sorted({(n if n >= 55 else n + 12) for n in c}) for c in chords]
        _pads(m, chords, 0, 1.15)
        _arp(m, chords, bell, [0, None, None, None, 2, None, None, None], 1.0, 4, 0.5, 12, 1.0)
        _melody(m, chords, [53 + s for s in MAJ_PENT], range(6, 16), bell, 72, 86, 0.4, 1.0, 0.6)
        m.put(m.voice(drone, 41, _hz(41), m.dur(64)), 0, 0, dry=0.5, wet=0.2)
        return m.finish(0.7, 3.4, 0.4)
    if style == "clean-tech":
        chords, roots = _key(57, [(0, "min7"), (-4, "maj7"), (-9 + 12, "maj"), (-2, "maj")], 60)
        _pads(m, chords, 0, 0.7)
        _arp(m, chords, pluck, [0, 2, 1, 2, 3, 2, 1, 2, 0, 2, 1, 2, 3, 2, 1, 4], 0.25, 2, 0.5, 0, 0.3)
        _bass_line(m, roots, [(0, 0.45, 0), (0.5, 0.45, 0), (1.5, 0.45, 12), (2, 0.45, 0), (2.5, 0.45, 0),
                              (3.5, 0.45, 7)], 4, 0.65)
        _drums(m, 6, [0, 1, 2, 3], [], [0.5, 1.5, 2.5, 3.5], [0.25, 0.75, 1.25, 1.75, 2.25, 2.75, 3.25, 3.75],
               0.0, 0.5)
        return m.finish(0.22, 1.3, 0.75)
    if style == "playful":
        chords, roots = _key(60, [(0, "maj"), (7, "maj"), (9, "min"), (5, "maj")], 62)
        chords = [[n if n < 72 else n - 12 for n in c] for c in chords]
        _arp(m, chords, pluck, [None, 0, None, 1, None, 2, None, 1], 0.5, 0, 0.6, 0, 0.25)
        _bass_line(m, roots, [(0, 0.8, 0), (1, 0.8, 7), (2, 0.8, 0), (3, 0.8, 7)], 2, 0.6, 36)
        _drums(m, 4, [], [1, 3], [], [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5], 0.0, 0.5)
        _melody(m, chords, [60 + s for s in MAJ_PENT], range(0, 16), marimba, 72, 86, 0.75, 0.3, 0.3)
        return m.finish(0.2, 1.1, 0.8)
    if style == "lofi-study":
        chords, roots = _key(50, [(0, "min7"), (5, "dom7"), (10, "maj7"), (7, "min7")], 58)
        chords = [sorted({(n if n >= 55 else n + 12) for n in c}) for c in chords]
        for bar in range(BARS):
            ch = chords[bar % 4]
            for i, b in enumerate((0, 1.5, 2.5)):
                for k, note in enumerate(ch[: 4]):
                    m.put(m.voice(epiano, note, _hz(note), m.dur(1.2 if i < 2 else 1.4), 0.8),
                          m.sec(bar, b + 0.015 * k), -0.2 + 0.15 * k, dry=0.5 if i else 0.6, wet=0.35)
        _bass_line(m, roots, [(0, 1.4, 0), (2.5, 1.0, 7)], 0, 0.6, 38)
        _drums(m, 2, [0, 2.5], [1, 3], [0.5, 1, 1.5, 2, 2.5, 3, 3.5], [], 0.16, 0.6)
        _melody(m, chords, [50 + s for s in MIN_PENT], range(8, 16), epiano, 70, 82, 0.4, 0.5, 0.3)
        return m.finish(0.3, 1.6, 0.45, extra=vinyl(m.n, 5))
    raise KeyError(style)


# ---- files -------------------------------------------------------------------------------------

def track(style: str) -> Path:
    """Path of the style's loop (a WAV), made on first use."""
    if style not in STYLES:
        raise KeyError(f"Unknown music style: {style}")
    DIR.mkdir(parents=True, exist_ok=True)
    out = DIR / f"{style}-v{VERSION}.wav"
    if out.exists():
        return out
    pcm = _build(style)
    tmp = out.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    tmp.replace(out)
    return out


def seconds(style: str) -> float:
    return BARS * 4 * 60 / STYLES[style]["bpm"]


def preview(style: str, length: float = 22.0) -> Path:
    """A small AAC clip for the in-page player."""
    out = DIR / f"{style}-v{VERSION}-preview.m4a"
    if not out.exists():
        src = track(style)
        ff.run(["-i", src, "-t", f"{length:.1f}", "-af", f"afade=t=out:st={length - 2:.1f}:d=2", "-c:a", "aac",
                "-b:a", "128k", out], timeout=120)
    return out


def resolve(choice) -> Path | None:
    """A render option -> a file: 'builtin:<style>' or a path to one of the user's own tracks."""
    if not choice:
        return None
    s = str(choice)
    if s.startswith("builtin:"):
        return track(s.split(":", 1)[1])
    p = Path(s)
    return p if p.exists() else None

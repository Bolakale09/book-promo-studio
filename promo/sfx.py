"""Synthesised page-turn sounds (no downloads, no licences).

A real page turn has three parts, and each is built separately:
  1. lift  - dry crackle as the paper leaves the stack (sparse clicks + high rustle)
  2. swish - air moving past the sheet: band-passed noise whose pitch and loudness follow the page's speed
  3. flap  - the sheet landing: a soft low thump with a short papery slap
The sound pans right -> left with the page and gets a touch of room reverb. Every turn gets its own variation.
"""
import math
import wave
from pathlib import Path

import numpy as np

from . import config

SR = 44100
SFX_DIR = config.DATA / "sfx"
VERSION = 3  # bump to regenerate cached sounds after changing the recipe


def _svf_bandpass(x: np.ndarray, fc: np.ndarray, q: float) -> np.ndarray:
    """Band-pass with a centre frequency that changes every sample (Chamberlin state-variable filter)."""
    f = 2 * np.sin(np.pi * np.clip(fc, 20, SR / 6) / SR)
    out = np.empty_like(x)
    low = band = 0.0
    damp = 1.0 / q
    for i in range(len(x)):
        high = x[i] - low - damp * band
        band += f[i] * high
        low += f[i] * band
        out[i] = band
    return out


def _smooth(x: np.ndarray, n: int) -> np.ndarray:
    """Cheap low-pass (moving average of n samples)."""
    return np.convolve(x, np.ones(n) / n, "same") if n > 1 else x


def _fft_convolve(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n = len(a) + len(b) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, size) * np.fft.rfft(b, size), size)[:n]


def _room(sig: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Small-room reverb: a few early reflections + a short decaying noise tail."""
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-t / 0.06) * 0.035
    ir = _smooth(ir, 3)
    ir[0] = 1.0
    for delay, gain in ((0.011, 0.22), (0.019, 0.14), (0.031, 0.09)):
        ir[int(delay * SR)] += gain
    return _fft_convolve(sig, ir)


def _synth(duration: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    T = max(0.18, duration)
    tail = 0.35
    n = int((T + tail) * SR)
    t = np.arange(n) / SR
    x = np.clip(t / T, 0, 1)                      # turn progress 0..1
    speed = np.where(t < T, np.sin(np.pi * x) ** 1.3, 0.0)   # page speed with a sine ease
    tone = rng.uniform(0.85, 1.18)                # paper stiffness / size variation

    # 1. crackle: the paper flexing. A burst as it leaves the stack, then grains that follow the page's speed
    crackle = np.zeros(n)
    n_grains = int(rng.uniform(70, 110) * min(1.5, T / 0.85 + 0.3))
    weight = 0.35 * np.exp(-((np.linspace(0, 1, 400) - 0.06) / 0.07) ** 2) + np.sin(np.pi * np.linspace(0, 1, 400))
    weight /= weight.sum()
    for _ in range(n_grains):
        pos = rng.choice(400, p=weight) / 400 + rng.uniform(0, 1 / 400)
        i0 = int(pos * T * SR)
        g = int(rng.uniform(0.0006, 0.0035) * SR)
        if i0 + g >= n:
            continue
        grain = rng.standard_normal(g) * np.exp(-np.linspace(0, rng.uniform(3, 7), g))
        crackle[i0:i0 + g] += grain * rng.uniform(0.25, 1.0)
    crackle = np.diff(crackle, prepend=0.0) * 0.5    # keep it crisp and dry
    rustle = _smooth(np.diff(rng.standard_normal(n), prepend=0.0), 3) * 0.035 * np.clip(1 - x * 2.5, 0, 1) * (t < T)

    # 2. swish: soft air past the sheet, band-passed around a centre that rises with speed, with a grainy
    #    papery texture (random amplitude flutter) instead of a steady hiss
    noise = rng.standard_normal(n)
    fc = (380 + 1500 * speed) * tone
    grain = _smooth(rng.random(n), int(SR / 70))
    grain = 0.45 + 0.55 * (grain - grain.min()) / max(1e-9, np.ptp(grain))
    swish = _svf_bandpass(noise, fc, q=1.9) * (0.05 + 0.95 * speed) * grain * 0.42
    whoosh = _smooth(noise, 120) * 3.0 * speed ** 2  # low body of the moving air

    # 3. flap: landing thump + slap right at the end of the turn
    land = int(T * 0.97 * SR)
    flap = np.zeros(n)
    fl = int(0.09 * SR)
    tt = np.arange(fl) / SR
    thump = np.sin(2 * np.pi * rng.uniform(85, 130) * tt) * np.exp(-tt / 0.02) * 0.5
    slap = _smooth(rng.standard_normal(fl), 5) * np.exp(-tt / 0.01) * 0.95
    end = min(n, land + fl)
    flap[land:end] = (thump + slap)[:end - land] * rng.uniform(0.6, 1.0)

    mono = crackle + rustle + swish + whoosh + flap
    # gentle fade-in so it never clicks on
    mono[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))

    # pan right -> left following the sheet (equal-power), then room reverb
    pan = np.cos(np.pi * x) * 0.55                 # +0.55 (right) .. -0.55 (left)
    a = (pan + 1) * np.pi / 4
    left, right = mono * np.cos(a), mono * np.sin(a)
    left, right = _room(left, rng)[:n], _room(right, rng)[:n]
    st = np.stack([left, right], axis=1)
    st /= max(1e-6, np.abs(st).max())
    return st * 0.72


def page_turn(duration: float, variant: int = 0) -> Path:
    """Stereo WAV of one page turn lasting `duration` seconds (cached; 6 variations per duration)."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    ms = int(round(duration * 20)) * 50               # round to 50 ms so the cache stays small
    v = variant % 6
    out = SFX_DIR / f"turn_v{VERSION}_{ms}ms_{v}.wav"
    if out.exists():
        return out
    data = (_synth(ms / 1000, seed=ms * 31 + v) * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    return out

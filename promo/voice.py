"""Text-to-speech narration.

xAI Grok TTS (~$4.20 per 1M characters, returns word timings so captions need no transcription) or
OpenAI gpt-4o-mini-tts (~$12 per 1M characters). Chosen with TTS_PROVIDER.
"""
import base64
import hashlib
import json
from functools import lru_cache
from pathlib import Path

import requests

from . import budget, config
from .genres import GENRES, TTS_VOICES

XAI_VOICES = ["ara", "eve", "rex", "sal", "leo"]  # fallback if the voice list can't be fetched
XAI_GENRE_VOICE = {"fiction": "ara", "self-help": "rex", "poetry": "eve", "gift": "ara", "medical": "sal",
                   "engineering": "leo", "children": "eve"}


@lru_cache
def _xai_voice_list(key: str) -> tuple:
    try:
        r = requests.get("https://api.x.ai/v1/tts/voices", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        r.raise_for_status()
        ids = [v["voice_id"] for v in r.json().get("voices", []) if v.get("voice_id")]
        return tuple(ids) or tuple(XAI_VOICES)
    except Exception:
        return tuple(XAI_VOICES)


def voices() -> list[str]:
    if config.TTS_PROVIDER == "xai":
        return list(_xai_voice_list(config.XAI_API_KEY)) if config.XAI_API_KEY else XAI_VOICES
    return TTS_VOICES


def default_voice(genre: str) -> str:
    if config.TTS_PROVIDER == "xai":
        v = XAI_GENRE_VOICE.get(genre, "eve")
        return v if v in voices() else voices()[0]
    return GENRES[genre]["voice"]


def timings(wav: Path) -> list[dict] | None:
    """Word timings saved next to an xAI narration file (None for OpenAI audio)."""
    p = wav.with_suffix(".words.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def speak(text: str, voice: str, instructions: str, out_dir: Path, genre: str = "fiction") -> Path:
    provider = config.TTS_PROVIDER
    if voice not in voices():  # e.g. an OpenAI voice name while using xAI
        voice = default_voice(genre)
    key = hashlib.md5(f"{provider}|{config.TTS_MODEL}|{voice}|{instructions}|{text}".encode()).hexdigest()[:12]
    out = out_dir / f"vo_{key}.wav"
    if out.exists():
        return out
    chars = len(text) + (len(instructions) if provider == "openai" else 0)
    cost = budget.tts_cost(config.TTS_MODEL, chars)
    budget.guard(cost, "voiceover")
    if provider == "xai":
        _xai_speak(text, voice, out)
    else:
        _openai_speak(text, voice, instructions, out)
    budget.record("tts", config.TTS_MODEL, cost, text[:60])
    return out


def _openai_speak(text: str, voice: str, instructions: str, out: Path) -> None:
    from .llm import openai_client

    kwargs = dict(model=config.TTS_MODEL, voice=voice, input=text, response_format="wav")
    if config.TTS_MODEL.startswith("gpt-"):
        kwargs["instructions"] = instructions
    with openai_client().audio.speech.with_streaming_response.create(**kwargs) as r:
        r.stream_to_file(out)


def _xai_speak(text: str, voice: str, out: Path) -> None:
    if not config.XAI_API_KEY:
        raise RuntimeError("XAI_API_KEY is missing. Add it in Settings.")
    r = requests.post(
        "https://api.x.ai/v1/tts",
        headers={"Authorization": f"Bearer {config.XAI_API_KEY}", "Content-Type": "application/json"},
        json={"text": text, "voice_id": voice, "language": "en", "with_timestamps": True,
              "output_format": {"codec": "wav", "sample_rate": 24000}},
        timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"xAI voice failed ({r.status_code}): {r.text[:300]}")
    if r.headers.get("content-type", "").startswith("application/json"):
        data = r.json()
        out.write_bytes(base64.b64decode(data["audio"]))
        words = _words_from_chars(data.get("audio_timestamps") or {})
        if words:
            out.with_suffix(".words.json").write_text(json.dumps(words), encoding="utf-8")
    else:  # raw audio (no timings)
        out.write_bytes(r.content)


def _words_from_chars(ts: dict) -> list[dict]:
    """xAI gives a start/end per character; join them into words."""
    chars, times = ts.get("graph_chars") or [], ts.get("graph_times") or []
    words, cur, start, end = [], "", None, None
    for ch, t in zip(chars, times):
        t0, t1 = (t.get("start", 0.0), t.get("end", 0.0)) if isinstance(t, dict) else (t[0], t[-1])
        if ch.isspace():
            if cur:
                words.append({"word": cur, "start": start, "end": end})
            cur, start = "", None
            continue
        if start is None:
            start = t0
        cur += ch
        end = t1
    if cur:
        words.append({"word": cur, "start": start, "end": end})
    return words

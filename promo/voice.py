"""Text-to-speech for each scene (OpenAI gpt-4o-mini-tts: ~$0.006 per 30s video)."""
import hashlib
from pathlib import Path

from . import budget, config
from .llm import openai_client


def speak(text: str, voice: str, instructions: str, out_dir: Path) -> Path:
    key = hashlib.md5(f"{config.TTS_MODEL}|{voice}|{instructions}|{text}".encode()).hexdigest()[:12]
    out = out_dir / f"vo_{key}.wav"
    if out.exists():
        return out
    cost = budget.tts_cost(config.TTS_MODEL, len(text) + len(instructions))
    budget.guard(cost, "voiceover")
    kwargs = dict(model=config.TTS_MODEL, voice=voice, input=text, response_format="wav")
    if config.TTS_MODEL.startswith("gpt-"):
        kwargs["instructions"] = instructions
    with openai_client().audio.speech.with_streaming_response.create(**kwargs) as r:
        r.stream_to_file(out)
    budget.record("tts", config.TTS_MODEL, cost, text[:60])
    return out

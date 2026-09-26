"""Turn a reference video into a reusable 'format blueprint' (structure, not words)."""
import json
from datetime import datetime
from pathlib import Path

from . import config, ffmpeg_utils as ff, ingest, llm
from .genres import FIVE_RULES, GENRES
from .transcribe import transcribe

BLUEPRINT_SYSTEM = """You are a short-form video strategist who reverse-engineers viral TikTok/Reels/Shorts videos
that sell books. You extract the FORMAT (structure, pacing, hook mechanics, emotional arc, overlay style,
ending) so it can be re-used for a different book. Never copy the original's exact wording into the blueprint
fields except in 'original_hook' and 'original_overlays'. Respond with JSON only."""

BLUEPRINT_SHAPE = """{
  "summary": "one sentence describing the format",
  "original_hook": "exact first line / first overlay of the reference",
  "original_overlays": ["on-screen text lines you could read, in order"],
  "hook": {"type": "bold claim | curiosity gap | POV | contrarian | identity | question", "mechanic": "why it stops the scroll", "seconds": 2},
  "emotion": "the core feeling it sells",
  "structure": [{"beat": "name", "purpose": "what this beat does", "seconds": 3, "visual": "what is on screen", "text_style": "overlay/captions style"}],
  "total_seconds": 20,
  "pacing": "e.g. cut every 1.5-2s",
  "voice": {"has_voiceover": true, "style": "delivery style"},
  "overlay_style": "how on-screen text is used",
  "ending": {"type": "breadcrumb | question | loop | CTA", "description": "..."},
  "music": "mood / energy",
  "why_it_works": "2-3 sentences",
  "best_for_genres": ["fiction", "self-help", "poetry", "gift", "medical", "engineering", "children"],
  "score": {"hook": 1-10, "emotion": 1-10, "simplicity": 1-10, "cloneability": 1-10}
}"""


def analyze_reference(video: Path, progress=lambda msg: None) -> dict:
    folder = video.parent
    info = json.loads((folder / "info.json").read_text(encoding="utf-8")) if (folder / "info.json").exists() else {}

    progress("Extracting audio...")
    audio = ingest.extract_audio(video)
    progress("Transcribing speech (runs on your PC, free)...")
    tr = transcribe(audio)
    (folder / "transcript.json").write_text(json.dumps(tr, indent=1), encoding="utf-8")

    progress("Measuring shot pacing...")
    dur = ff.duration(video)
    cuts = ingest.shot_cuts(video)
    progress("Reading on-screen text...")
    frames = ingest.keyframes(video)

    user = f"""Reference video metadata: {json.dumps(info)[:1500]}
Duration: {dur:.1f}s. Shot cuts at (s): {cuts[:60]} ({len(cuts)} cuts -> avg shot {dur / (len(cuts) + 1):.1f}s).

Timed transcript of the voice / audio:
{json.dumps(tr['segments'])[:12000]}

The attached images are evenly spaced frames (filename = timestamp). Read any on-screen TEXT OVERLAYS - in many
viral book videos the whole script is text on screen, not voice.

These are the rules viral book videos follow:
{FIVE_RULES}

Return the blueprint JSON with this shape:
{BLUEPRINT_SHAPE}"""
    progress("Building the format blueprint with AI...")
    bp = llm.chat_json(BLUEPRINT_SYSTEM, user, images=frames, max_out=5000, what="blueprint analysis")
    bp["source"] = info.get("url") or info.get("title") or video.name
    bp["reference_title"] = info.get("title")
    bp["reference_duration"] = round(dur, 1)
    bp["transcript"] = tr["text"]
    bp["created"] = datetime.now().isoformat(timespec="seconds")
    save_blueprint(folder.name, bp)
    return bp


def save_blueprint(bp_id: str, bp: dict) -> None:
    (config.BLUEPRINTS_DIR / f"{bp_id}.json").write_text(json.dumps(bp, indent=1), encoding="utf-8")


def list_blueprints() -> dict[str, dict]:
    out = {}
    for p in sorted(config.BLUEPRINTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


def genre_label(key: str) -> str:
    return GENRES[key]["label"]

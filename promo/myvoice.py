"""Use your own voice as the narrator (optional).

You read the script into your microphone (or upload a recording). The app cleans it up (hum removed, levelled,
silence trimmed), listens to it to find when every word is spoken, and then times the scenes and captions to YOUR
recording instead of an AI voice. It is free: the listening runs on your PC, or costs a fraction of a cent through
xAI/OpenAI when the server can't do it.
"""
import difflib
import hashlib
import json
import re
from pathlib import Path

from . import book as bk, ffmpeg_utils as ff
from .transcribe import align_words, transcribe, _norm


def folder(book_id: str) -> Path:
    d = bk.book_dir(book_id) / "assets" / "myvoice"
    d.mkdir(parents=True, exist_ok=True)
    return d


def narration_text(variant: dict) -> str:
    """Everything the narrator says, scene by scene - what you need to read."""
    return " ".join((s.get("voiceover") or "").strip() for s in variant.get("scenes", [])
                    if (s.get("voiceover") or "").strip())


def script_lines(variant: dict) -> list[tuple[int, str, str]]:
    """(scene number, beat, text) for every spoken scene - shown as a teleprompter."""
    return [(i + 1, s.get("beat", ""), s["voiceover"].strip()) for i, s in enumerate(variant.get("scenes", []))
            if (s.get("voiceover") or "").strip()]


def text_hash(text: str) -> str:
    return hashlib.md5(" ".join(text.split()).lower().encode()).hexdigest()[:10]


def wav_path(book_id: str, script_id: str) -> Path:
    return folder(book_id) / f"{script_id}.wav"


def info_path(book_id: str, script_id: str) -> Path:
    return folder(book_id) / f"{script_id}.json"


CLEAN = ("highpass=f=75,afftdn=nf=-28,acompressor=threshold=-21dB:ratio=2.5:attack=8:release=140:makeup=3,"
         "loudnorm=I=-16:TP=-1.5:LRA=9,"
         "silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.08,"
         "areverse,silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.08,areverse")


def save(book_id: str, script_id: str, data: bytes, filename: str, variant: dict, clean: bool = True) -> dict:
    """Store a recording for this script (any common audio format). Returns its info."""
    src = folder(book_id) / f"_upload{Path(filename).suffix.lower() or '.wav'}"
    src.write_bytes(data)
    out = wav_path(book_id, script_id)
    tmp = out.with_name(out.stem + ".part.wav")
    try:
        args = ["-i", src, "-vn"]
        if clean:
            args += ["-af", CLEAN]
        ff.run([*args, "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", tmp], timeout=300)
        tmp.replace(out)
    finally:
        src.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
    text = narration_text(variant)
    info = {"created": __import__("time").strftime("%Y-%m-%d %H:%M"), "seconds": round(ff.duration(out), 2),
            "text_hash": text_hash(text), "cleaned": clean, "name": filename[:60]}
    info_path(book_id, script_id).write_text(json.dumps(info), encoding="utf-8")
    return info


def info(book_id: str, script_id: str, variant: dict | None = None) -> dict | None:
    """Saved recording details, plus whether the script has changed since it was recorded."""
    p, w = info_path(book_id, script_id), wav_path(book_id, script_id)
    if not (p.exists() and w.exists()):
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    d["path"] = str(w)
    if variant is not None:
        d["script_changed"] = d.get("text_hash") != text_hash(narration_text(variant))
    return d


def remove(book_id: str, script_id: str) -> None:
    for p in (wav_path(book_id, script_id), info_path(book_id, script_id)):
        p.unlink(missing_ok=True)
    for p in folder(book_id).glob(f"{script_id}.words-*.json"):
        p.unlink(missing_ok=True)


def analyse(wav: Path, text: str) -> dict:
    """Listen to the recording: when is each word of `text` spoken, and how well does it match the script?
    Cached next to the recording so re-renders don't listen again."""
    key = text_hash(text)
    cache = wav.with_name(f"{wav.stem}.words-{key}.json")
    if cache.exists() and cache.stat().st_mtime >= wav.stat().st_mtime:
        return json.loads(cache.read_text(encoding="utf-8"))
    heard = transcribe(wav)["words"]
    a = [_norm(t) for t in text.split()]
    b = [_norm(w["word"]) for w in heard]
    matched = sum(blk.size for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    words = align_words(text, wav, heard)
    out = {"words": words, "match": round(matched / max(1, len(a)), 3), "seconds": round(ff.duration(wav), 2)}
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out


def clip(wav: Path, start: float, end: float, out: Path) -> Path:
    """Cut one stretch of the recording (a run of voiced scenes) into its own file."""
    ff.run(["-i", wav, "-ss", f"{max(0.0, start):.3f}", "-to", f"{end:.3f}", "-c:a", "pcm_s16le", out], timeout=120)
    return out


def takes(wav: Path, runs: list[list[str]], assets: Path, progress) -> list[tuple[Path, list[dict]]]:
    """One (audio file, word timings) per run of spoken scenes, cut from a single recording.
    `runs` = the voiceover text of each scene in each run. Word times are relative to each clip."""
    text = " ".join(" ".join(r) for r in runs)
    progress("Listening to your recording...")
    words = analyse(wav, text)["words"]
    total = ff.duration(wav)
    out, i = [], 0
    for k, run in enumerate(runs):
        n = sum(len(t.split()) for t in run)
        chunk = words[i:i + n]
        i += n
        if not chunk:
            raise RuntimeError("Your recording is shorter than the script - record the whole script.")
        start = max(0.0, chunk[0]["start"] - 0.12)
        end = min(total, chunk[-1]["end"] + 0.28)
        if len(runs) == 1:
            start, end = 0.0, total
        path = clip(wav, start, end, assets / f"mine_{wav.stem}_{k}.wav") if len(runs) > 1 else wav
        shifted = [{**w, "start": round(w["start"] - start, 3), "end": round(w["end"] - start, 3)} for w in chunk]
        out.append((path, shifted))
    return out

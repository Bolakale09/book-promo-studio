"""Speech-to-text with word timestamps. Runs locally for free (faster-whisper); falls back to OpenAI."""
import difflib
import re
from functools import lru_cache
from pathlib import Path

from . import budget, config, ffmpeg_utils as ff


@lru_cache
def _local_model():
    from faster_whisper import WhisperModel
    return WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")


_local_broken = False  # model could not be loaded/downloaded this session - don't retry every time


def transcribe(audio: Path) -> dict:
    """Returns {"text", "segments": [{start,end,text}], "words": [{word,start,end}]}.
    Free local model first; OpenAI whisper-1 (~$0.006/min) if it isn't available (e.g. Hugging Face unreachable)."""
    global _local_broken
    if not _local_broken:
        try:
            return _transcribe_local(audio)
        except Exception:
            _local_broken = True
    if not config.OPENAI_API_KEY:
        raise RuntimeError("Local transcription is unavailable and no OPENAI_API_KEY is set.")
    return _transcribe_openai(audio)


def _transcribe_local(audio: Path) -> dict:
    segs, _ = _local_model().transcribe(str(audio), word_timestamps=True, vad_filter=False)
    segments, words = [], []
    for s in segs:
        segments.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()})
        for w in s.words or []:
            words.append({"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})
    return {"text": " ".join(s["text"] for s in segments), "segments": segments, "words": words}


def _transcribe_openai(audio: Path) -> dict:
    from .llm import openai_client

    minutes = ff.duration(audio) / 60
    cost = minutes * budget.WHISPER_PER_MIN
    budget.guard(cost, "transcription")
    with open(audio, "rb") as f:
        r = openai_client().audio.transcriptions.create(
            model="whisper-1", file=f, response_format="verbose_json",
            timestamp_granularities=["word", "segment"])
    budget.record("transcribe", "whisper-1", cost, audio.name)
    segments = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in (r.segments or [])]
    words = [{"word": w.word, "start": w.start, "end": w.end} for w in (r.words or [])]
    return {"text": r.text, "segments": segments, "words": words}


# ---- aligning known script text to audio -------------------------------------

def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def align_words(script_text: str, audio: Path) -> list[dict]:
    """Give every word of `script_text` a start/end time in `audio`.

    We know exactly what the voice says (we wrote it), so we transcribe the TTS audio and
    match the words; unmatched words are interpolated. Falls back to even spacing by length.
    """
    tokens = script_text.split()
    if not tokens:
        return []
    total = ff.duration(audio)
    try:
        heard = transcribe(audio)["words"]
    except Exception:
        heard = []

    times: list[tuple[float, float] | None] = [None] * len(tokens)
    if heard:
        a = [_norm(t) for t in tokens]
        b = [_norm(w["word"]) for w in heard]
        for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
            for k in range(blk.size):
                w = heard[blk.b + k]
                times[blk.a + k] = (w["start"], w["end"])

    if not any(times):  # nothing matched: spread by character length
        lens = [len(t) + 2 for t in tokens]
        scale, t = total / sum(lens), 0.0
        for i, n in enumerate(lens):
            times[i] = (t, t + n * scale)
            t += n * scale
    else:  # fill gaps between known anchors
        i = 0
        while i < len(tokens):
            if times[i] is not None:
                i += 1
                continue
            j = i
            while j < len(tokens) and times[j] is None:
                j += 1
            left = times[i - 1][1] if i > 0 else 0.0
            right = times[j][0] if j < len(tokens) else total
            step = max(right - left, 0.05) / (j - i)
            for k in range(i, j):
                times[k] = (left + (k - i) * step, left + (k - i + 1) * step)
            i = j

    return [{"word": tok, "start": round(s, 3), "end": round(max(e, s + 0.05), 3)}
            for tok, (s, e) in zip(tokens, times)]

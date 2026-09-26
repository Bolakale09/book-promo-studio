"""AI quality check: a vision model looks at every AI shot (and then the finished video) for the flaws that make
viewers scroll away - warped hands/faces, garbled text, melting objects, identity drift - and bad shots are
re-made with a corrected prompt before the final video is assembled.

Each check costs about $0.002-0.01. Verdicts are cached next to the asset, so re-rendering never pays twice.
"""
import json
import tempfile
from pathlib import Path

from PIL import Image

from . import budget, ffmpeg_utils as ff, llm

PASS_SCORE = 7      # 1-10; below this the shot is re-made
FINAL_PASS = 6      # looser bar for the whole-video look-through (text overlays are expected there)

REVIEW_SYSTEM = """You are a strict visual quality reviewer for realistic short-form promo videos (TikTok/Reels).
You catch AI-generation flaws that make a video look fake or cheap:
- hands/fingers (extra, missing, fused, bent wrong), limbs, anatomy, posture
- faces: warped eyes, teeth, asymmetry, plastic/waxy skin, uncanny expression
- garbled or fake text, letters, logos, watermarks, signage (there should be NO text in the shot)
- melted, merged or impossible objects, broken physics, duplicated people or objects
- a named character who does not match the reference photo / description
- off-brief: the shot does not show what the scene needs
- for several frames of ONE video clip: identity drift, morphing, flicker between frames
- not realistic (looks like a render, cartoon or illustration when a real photo was asked for), blurry, low detail
Judge like a picky viewer on a phone. Respond with JSON only."""

VERDICT_SHAPE = """{
  "score": 1-10,            // 10 = indistinguishable from a real photo/video and exactly on brief
  "problems": ["short, specific flaw", "..."],   // empty if none
  "fixed_prompt": "a rewritten generation prompt that avoids every problem (e.g. hands out of frame, simpler
                   composition, one person, no visible text, closer framing), keeping the same story beat"
}"""


def _thumb(path: Path, max_side: int = 768) -> Path:
    img = Image.open(path).convert("RGB")
    img.thumbnail((max_side, max_side))
    out = Path(tempfile.mkdtemp()) / (path.stem + ".jpg")
    img.save(out, quality=85)
    return out


def video_frames(video: Path, n: int = 4) -> list[Path]:
    dur = ff.duration(video)
    d = Path(tempfile.mkdtemp())
    out = []
    for i in range(n):
        t = dur * (0.08 + 0.84 * i / max(1, n - 1))
        p = d / f"f{i}.jpg"
        ff.run(["-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", "scale=432:-2", "-q:v", "4", p])
        out.append(p)
    return out


def _cache(asset: Path) -> Path:
    return asset.with_name(asset.name + ".qa.json")


def review(asset: Path, kind: str, intent: str, refs: list[Path] | None = None) -> dict:
    """Score one AI photo (kind='image') or AI clip (kind='video'). Never raises: a failed check passes the shot."""
    cache = _cache(asset)
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        imgs = video_frames(asset) if kind == "video" else [_thumb(asset)]
        refs = [_thumb(r, 512) for r in (refs or []) if r and Path(r).exists()]
        what = ("These are 4 frames (in order) from ONE AI-generated video clip." if kind == "video"
                else "This is ONE AI-generated photo.")
        if refs:
            what += " The LAST image is the character's reference photo - the person must match it."
        user = f"""{what}
The shot was generated from this brief:
\"\"\"{intent}\"\"\"

Review it and return JSON:
{VERDICT_SHAPE}"""
        v = llm.chat_json(REVIEW_SYSTEM, user, images=imgs + refs, max_out=1200, what=f"quality check ({kind})")
        v = {"score": int(v.get("score") or 0), "problems": list(v.get("problems") or [])[:6],
             "fixed_prompt": (v.get("fixed_prompt") or "").strip()}
    except budget.BudgetExceeded:
        return {"score": 10, "problems": [], "fixed_prompt": "", "skipped": "budget"}
    except Exception as e:
        return {"score": 10, "problems": [], "fixed_prompt": "", "skipped": str(e)[:120]}
    cache.write_text(json.dumps(v), encoding="utf-8")
    return v


def best_of(generate, prompt: str, kind: str, refs: list[Path] | None, tries: int, label: str, progress) -> tuple:
    """generate(prompt, take) -> Path. Make the shot, check it, re-make with the reviewer's fixed prompt until it
    passes or the tries run out. Returns (best path, report)."""
    report = {"scene": label, "kind": kind, "takes": []}
    best, best_score = None, -1
    p = prompt
    for take in range(tries + 1):
        path = generate(p, take)
        progress(f"{label}: checking the AI {kind} for flaws...")
        v = review(path, kind, p, refs)
        report["takes"].append({"score": v["score"], "problems": v["problems"], "prompt": p[:300]})
        if v["score"] > best_score:
            best, best_score = path, v["score"]
        if v["score"] >= PASS_SCORE or v.get("skipped"):
            break
        if take < tries:
            progress(f"{label}: scored {v['score']}/10 ({'; '.join(v['problems'][:2])}) - re-making it...")
            p = v["fixed_prompt"] or f"{prompt}. Simple composition, hands out of frame, no text anywhere."
    report["final_score"] = best_score
    report["fixed"] = len(report["takes"]) > 1 and best_score >= PASS_SCORE
    return best, report


FINAL_SYSTEM = """You are the final quality reviewer of a vertical promo video for a book, before it is published.
You see one frame from each scene, in order. These are INTENDED and are not problems:
- a short text overlay near the top, and big captions that show the narration only 1-3 words at a time
  (a caption showing part of a sentence is normal)
- 'page'/'flip' scenes: a real manuscript page of the author's book on a desk (the text is the book's actual
  text; pages may be turning); only flag them if the page is unreadable, black or broken
- the book cover scene
Flag real problems only:
- AI flaws in photos/footage (warped hands/faces, garbled text inside the photo, melted objects, fake look)
- footage that does not fit the scene brief or the book, looks like a different video, or has a watermark/logo
- black, frozen, blank or broken frames
- overlay/caption text that is cut off or unreadable
Respond with JSON only."""


def review_final(frames: list[tuple[int, Path, str]]) -> dict:
    """frames = [(scene index, frame image, 'visual type + brief')]. Returns {scene_index: verdict}."""
    try:
        listing = "\n".join(f"Image {k + 1} = scene {i + 1}: {desc}" for k, (i, _, desc) in enumerate(frames))
        user = f"""{listing}

Return JSON: {{"scenes": [{{"scene": 1, "score": 1-10, "problems": ["..."], "fixed_prompt": "better generation
prompt if the scene is an AI shot, else empty"}}], "summary": "one sentence"}}
Include every scene."""
        v = llm.chat_json(FINAL_SYSTEM, user, images=[_thumb(p, 640) for _, p, _ in frames], max_out=2500,
                          what="final video check")
    except Exception as e:
        return {"summary": f"Final check skipped: {str(e)[:120]}", "scenes": {}}
    out = {}
    for sv in v.get("scenes", []):
        try:
            out[int(sv["scene"]) - 1] = {"score": int(sv.get("score") or 10), "problems": sv.get("problems") or [],
                                         "fixed_prompt": (sv.get("fixed_prompt") or "").strip()}
        except (KeyError, ValueError, TypeError):
            continue
    return {"summary": v.get("summary", ""), "scenes": out}

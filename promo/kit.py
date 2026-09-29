"""Posting kit: everything you need to post a finished video - a thumbnail (in three shapes), a captions file
(.srt/.vtt, for uploading real subtitles), the video re-shaped to 4:5 and 1:1 for Instagram and Facebook feeds, and
ready-to-paste post text for each platform. Files go in a `kit/` folder next to the video and are re-made on demand
(so they are not synced to the cloud)."""
import json
import re
import zipfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from . import brand, ffmpeg_utils as ff

PLATFORMS = ["TikTok", "Instagram Reels", "YouTube Shorts"]
SIZES = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080)}
MODES = {"fit": "Whole video, soft blurred sides", "crop": "Cropped to fill (loses the top and bottom)"}


def kit_dir(render_dir: str | Path) -> Path:
    d = Path(render_dir) / "kit"
    d.mkdir(exist_ok=True)
    return d


def _meta(render_dir: str | Path) -> dict:
    return json.loads((Path(render_dir) / "render.json").read_text(encoding="utf-8"))


def video_path(render_dir: str | Path) -> Path:
    return Path(render_dir) / (_meta(render_dir).get("file") or "final.mp4")


# ---- captions file -----------------------------------------------------------------------

def words_for(render_dir: str | Path) -> tuple[list[dict], bool]:
    """(word timings, exact?). Videos made before timings were saved get an approximate timeline instead."""
    d = Path(render_dir)
    try:
        return json.loads((d / "words.json").read_text(encoding="utf-8")), True
    except (OSError, json.JSONDecodeError):
        pass
    meta = _meta(d)
    scenes = (meta.get("variant") or {}).get("scenes") or []
    out = []
    for i, tl in enumerate(meta.get("timeline") or []):
        vo = (scenes[i].get("voiceover") if i < len(scenes) else "") or ""
        ws = vo.split()
        if not ws:
            continue
        start = tl["start"] + 0.25
        span = max(0.8, tl["dur"] - 0.6)
        step = span / len(ws)
        for k, w in enumerate(ws):
            out.append({"word": w, "start": start + k * step, "end": start + (k + 1) * step - 0.03, "scene": i})
    return out, False


def cues(words: list[dict], max_chars: int = 38, max_words: int = 7, max_secs: float = 3.4) -> list[tuple]:
    """Group words into readable subtitle lines: (start, end, text)."""
    out, cur = [], []

    def flush():
        if cur:
            out.append((cur[0]["start"], cur[-1]["end"] + 0.12, " ".join(w["word"] for w in cur)))
            cur.clear()

    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        text = " ".join(x["word"] for x in cur)
        if (nxt is None or len(cur) >= max_words or len(text) + len(nxt["word"]) > max_chars
                or re.search(r"[.!?…]$", w["word"]) or nxt["start"] - w["end"] > 0.6
                or nxt.get("scene") != w.get("scene") and len(cur) >= 3
                or nxt["end"] - cur[0]["start"] > max_secs):
            flush()
    out = [(s, e, t) for s, e, t in out if t.strip()]
    return [(s, min(e, out[i + 1][0] - 0.02) if i + 1 < len(out) else e, t) for i, (s, e, t) in enumerate(out)]


def _ts(t: float, comma: bool) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{',' if comma else '.'}{ms:03d}"


def to_srt(items: list[tuple]) -> str:
    return "\n".join(f"{i}\n{_ts(s, True)} --> {_ts(e, True)}\n{t}\n" for i, (s, e, t) in enumerate(items, 1))


def to_vtt(items: list[tuple]) -> str:
    return "WEBVTT\n\n" + "\n".join(f"{_ts(s, False)} --> {_ts(e, False)}\n{t}\n" for s, e, t in items)


def write_captions(render_dir: str | Path) -> dict:
    words, exact = words_for(render_dir)
    items = cues(words)
    d = kit_dir(render_dir)
    (d / "captions.srt").write_text(to_srt(items), encoding="utf-8")
    (d / "captions.vtt").write_text(to_vtt(items), encoding="utf-8")
    return {"lines": len(items), "exact": exact}


# ---- thumbnails ---------------------------------------------------------------------------

def candidate_times(render_dir: str | Path) -> list[float]:
    """Moments worth using as a cover: shortly into each scene (after its opening animation has settled)."""
    meta = _meta(render_dir)
    total = float(meta.get("seconds") or 0)
    times = []
    for tl in meta.get("timeline") or []:
        times.append(round(min(tl["start"] + min(0.9, tl["dur"] * 0.4), max(0.0, total - 0.2)), 2))
    return times


def candidate_frames(render_dir: str | Path) -> list[tuple[float, Path]]:
    """Small preview images of every candidate cover."""
    d = kit_dir(render_dir)
    video = video_path(render_dir)
    out = []
    for k, t in enumerate(candidate_times(render_dir)):
        p = d / f"cand_{k:02d}.jpg"
        if not p.exists() or p.stat().st_mtime < video.stat().st_mtime:
            ff.run(["-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", "scale=270:-2", "-q:v", "5", p], timeout=60)
        out.append((t, p))
    return out


def reframe(img: Image.Image, size: tuple, mode: str = "fit") -> Image.Image:
    w, h = size
    img = img.convert("RGB")
    if img.size == size:
        return img
    if mode == "crop":
        return ImageOps.fit(img, size, Image.LANCZOS, centering=(0.5, 0.5))
    bg = ImageOps.fit(img, size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", size, (0, 0, 0)), 0.35)
    fg = img.resize((round(img.width * h / img.height), h), Image.LANCZOS) if img.width / img.height < w / h \
        else img.resize((w, round(img.height * w / img.width)), Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return bg


def make_thumbnails(render_dir: str | Path, t: float | None = None, title: str = "", mode: str = "fit") -> list[Path]:
    """A cover image in each shape (9:16, 4:5, 1:1) from the frame at time `t`, with an optional title on top."""
    from . import render as rd
    d = kit_dir(render_dir)
    if t is None:
        cands = candidate_times(render_dir)
        t = cands[0] if cands else 0.5
    src = d / "_frame.png"
    ff.run(["-ss", f"{t:.2f}", "-i", video_path(render_dir), "-frames:v", "1", src], timeout=60)
    frame = Image.open(src).convert("RGB")
    src.unlink(missing_ok=True)
    out = []
    for name, size in SIZES.items():
        img = reframe(frame, size, mode)
        if title.strip():
            card = rd.text_card(title.strip(), "Arial Black", int(size[0] * 0.075), "box", int(size[0] * 0.84))
            img.paste(card, ((size[0] - card.width) // 2, int(size[1] * 0.12)), card)
        p = d / f"thumbnail-{name.replace(':', 'x')}.jpg"
        img.save(p, quality=93)
        out.append(p)
    return out


# ---- reshaped videos ----------------------------------------------------------------------

def video_filter(size: tuple, mode: str) -> str:
    w, h = size
    if mode == "crop":
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    return (f"split[a][b];[a]scale=w={w // 12}:h={h // 12}:force_original_aspect_ratio=increase,crop={w // 12}:{h // 12},"
            f"boxblur=2:1,scale={w}:{h}:flags=bicubic,eq=brightness=-0.12[bg];"
            f"[b]scale=w={w}:h={h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")


def make_video(render_dir: str | Path, ratio: str, mode: str = "fit") -> Path:
    if ratio not in SIZES or ratio == "9:16":
        raise ValueError(f"Unsupported shape {ratio}")
    out = kit_dir(render_dir) / f"video-{ratio.replace(':', 'x')}.mp4"
    tmp = out.with_name(out.stem + ".part.mp4")
    ff.run(["-i", video_path(render_dir), "-filter_complex" if mode == "fit" else "-vf", video_filter(SIZES[ratio], mode),
            "-c:v", "libx264", "-preset", "faster", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy",
            "-movflags", "+faststart", tmp], timeout=1200)
    tmp.replace(out)
    return out


# ---- post text ----------------------------------------------------------------------------

def post_texts(book: dict, variant: dict, kit: dict | None = None) -> dict[str, str]:
    """Ready-to-paste text for each platform, with your brand hashtags and call-to-action."""
    kit = kit if kit is not None else brand.load()
    caption = (variant.get("post_caption") or "").strip()
    tags = brand.merge_hashtags(variant.get("hashtags") or [], kit, limit=8)
    buy = (book.get("where_to_buy") or "").strip()
    cta = (kit.get("cta") or "").strip()
    hook = ((variant.get("scenes") or [{}])[0].get("overlay") or variant.get("name") or book["title"]).strip()
    tail = " ".join(x for x in [cta, f"Find it: {buy}" if buy and buy.lower() not in cta.lower() else ""] if x)
    tk = "\n\n".join(x for x in [caption, tail, " ".join(tags[:5])] if x)
    ig = "\n\n".join(x for x in [caption, tail, " ".join(tags[:8])] if x)
    title = (hook if len(hook) <= 88 else hook[:85] + "...")
    yt_tags = ["#Shorts"] + [t for t in tags if t.lower() != "#shorts"][:4]
    yt = f"TITLE\n{title} #Shorts\n\nDESCRIPTION\n" + "\n\n".join(x for x in [caption, tail, " ".join(yt_tags)] if x)
    return {"TikTok": tk, "Instagram Reels": ig, "YouTube Shorts": yt}


def write_post_text(render_dir: str | Path, book: dict) -> Path:
    meta = _meta(render_dir)
    texts = post_texts(book, meta.get("variant") or {})
    body = "\n\n".join(f"===== {p} =====\n{t}" for p, t in texts.items()) + "\n"
    p = kit_dir(render_dir) / "post-text.txt"
    p.write_text(body, encoding="utf-8")
    return p


# ---- everything ---------------------------------------------------------------------------

def instant(book: dict, render_dir: str | Path, t: float | None = None, title: str = "", mode: str = "fit") -> dict:
    """The parts that take seconds: captions file, thumbnails and post text."""
    cap = write_captions(render_dir)
    thumbs = make_thumbnails(render_dir, t, title, mode)
    write_post_text(render_dir, book)
    pack(render_dir)
    return {"captions": cap, "thumbnails": [p.name for p in thumbs]}


def make_videos(render_dir: str | Path, ratios: list[str], mode: str = "fit", progress=lambda m, f=None: None) -> list[Path]:
    out = []
    for i, r in enumerate(ratios):
        progress(f"Making the {r} video...", i / max(1, len(ratios)))
        out.append(make_video(render_dir, r, mode))
    pack(render_dir)
    return out


def files(render_dir: str | Path) -> list[Path]:
    d = Path(render_dir) / "kit"
    if not d.exists():
        return []
    keep = ("captions.srt", "captions.vtt", "post-text.txt")
    return sorted(p for p in d.iterdir()
                  if p.name in keep or p.name.startswith(("thumbnail-", "video-")) and not p.name.endswith(".part.mp4"))


def pack(render_dir: str | Path) -> Path | None:
    """One zip with everything made so far."""
    items = files(render_dir)
    if not items:
        return None
    z = kit_dir(render_dir) / "posting-kit.zip"
    tmp = z.with_name("posting-kit.part.zip")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED if any(p.suffix == ".mp4" for p in items) else zipfile.ZIP_DEFLATED) as zf:
        for p in items:
            zf.write(p, p.name)
    tmp.replace(z)
    return z

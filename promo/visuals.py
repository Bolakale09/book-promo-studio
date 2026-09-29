"""Get the picture for each scene: AI photos, AI video, stock footage, own B-roll, pages, cover."""
import base64
import hashlib
import time
from pathlib import Path

import requests
from PIL import Image

from . import book as bk, budget, config
from .llm import image_data_uri, openai_client

REALISM = ("Photorealistic, candid, shot on a modern phone camera, natural light, shallow depth of field, "
           "real skin texture, vertical 9:16 composition, no text, no logos, no watermarks.")


def _key(*parts) -> str:
    return hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:12]


# ---- AI images ---------------------------------------------------------------------

def ai_image(prompt: str, out_dir: Path, ref_images: list[Path] | None = None, take: int = 0) -> Path:
    """`take` > 0 forces a fresh generation (used by the quality check to re-make a flawed shot)."""
    ref_images = [p for p in (ref_images or []) if p and Path(p).exists()]
    parts = [config.IMAGE_MODEL, config.IMAGE_QUALITY, prompt, *ref_images] + ([f"take{take}"] if take else [])
    out = out_dir / f"img_{_key(*parts)}.png"
    if out.exists():
        return out
    full = f"{prompt}\n\n{REALISM}"
    cost = budget.image_cost(config.IMAGE_MODEL, config.IMAGE_QUALITY)
    budget.guard(cost, "AI image")
    if config.IMAGE_PROVIDER == "xai":
        data = _xai_image(full, ref_images)
    else:
        data = _openai_image(full, ref_images)
    out.write_bytes(data)
    budget.record("image", config.IMAGE_MODEL, cost, prompt[:60])
    return out


def _openai_image(prompt: str, refs: list[Path]) -> bytes:
    client = openai_client()
    common = dict(model=config.IMAGE_MODEL, prompt=prompt, size="1024x1536", quality=config.IMAGE_QUALITY, n=1)
    if refs:
        files = [open(p, "rb") for p in refs[:4]]
        try:
            r = client.images.edit(image=files, **common)
        finally:
            for f in files:
                f.close()
    else:
        r = client.images.generate(**common)
    return base64.b64decode(r.data[0].b64_json)


def _xai_image(prompt: str, refs: list[Path]) -> bytes:
    headers = {"Authorization": f"Bearer {config.XAI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": config.IMAGE_MODEL, "prompt": prompt, "n": 1, "aspect_ratio": "9:16",
            "response_format": "b64_json"}
    url = "https://api.x.ai/v1/images/generations"
    if refs:
        url = "https://api.x.ai/v1/images/edits"
        body["image"] = {"url": image_data_uri(refs[0])}
    r = requests.post(url, json=body, headers=headers, timeout=180)
    r.raise_for_status()
    item = r.json()["data"][0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    return requests.get(item["url"], timeout=120).content


def character_prompt(book: dict, name: str, action: str) -> tuple[str, list[Path]]:
    c = next((c for c in book.get("characters", []) if c["name"] == name), None)
    if not c:
        return action, []
    refs = [bk.book_dir(book["id"]) / c["ref_image"]] if c.get("ref_image") else []
    prompt = (f"{action}\n\nThe person is {c['name']}: {c.get('description', '')}. "
              + ("Keep the exact same face, hair and look as the person in the reference image." if refs else ""))
    return prompt, refs


def make_character_reference(book: dict, char: dict) -> Path:
    """Create a portrait once, then use it as the reference so the character looks the same in every video."""
    d = bk.book_dir(book["id"]) / "characters"
    d.mkdir(exist_ok=True)
    img = ai_image(f"Portrait photo of {char['name']}: {char.get('description', '')}. Upper body, facing camera, "
                   f"neutral soft background, even lighting.", d)
    return img


def make_background(book: dict) -> Path:
    world = (book.get("digest") or {}).get("visual_world", "")
    img = ai_image("Top-down photo of an empty wooden reading desk, warm lamp light, a coffee mug and a pen at the "
                   f"edges, the centre left empty for a book. Mood: {world[:200]}", bk.book_dir(book["id"]))
    book["background"] = img.name
    fresh = bk.load(book["id"])  # keep edits made while the photo was being created
    fresh["background"] = img.name
    bk.save(fresh)
    return img


# ---- AI video (optional, the most expensive part) ----------------------------------------

def ai_video(prompt: str, seconds: float, out_dir: Path, start_image: Path | None = None,
             progress=lambda m: None, take: int = 0) -> Path:
    secs = int(max(2, min(10, round(seconds + 0.5))))
    parts = [config.VIDEO_MODEL, prompt, secs, start_image] + ([f"take{take}"] if take else [])
    out = out_dir / f"vid_{_key(*parts)}.mp4"
    if out.exists():
        return out
    cost = budget.video_cost(config.VIDEO_MODEL, secs)
    budget.guard(cost, f"{secs}s AI video")
    full = f"{prompt}\n\n{REALISM} Smooth, subtle, realistic camera motion."
    if config.VIDEO_PROVIDER == "openai":
        _openai_video(full, secs, out, start_image, progress)
    else:
        _xai_video(full, secs, out, start_image, progress)
    budget.record("video", config.VIDEO_MODEL, cost, prompt[:60])
    return out


def _xai_video(prompt: str, secs: int, out: Path, start_image: Path | None, progress) -> None:
    headers = {"Authorization": f"Bearer {config.XAI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": config.VIDEO_MODEL, "prompt": prompt, "duration": secs, "aspect_ratio": "9:16",
            "resolution": config.VIDEO_RESOLUTION, "generate_audio": False}
    if start_image:
        body["image"] = {"url": image_data_uri(start_image)}
    r = requests.post("https://api.x.ai/v1/videos/generations", json=body, headers=headers, timeout=120)
    r.raise_for_status()
    req_id = r.json()["request_id"]
    for i in range(120):  # up to ~10 minutes
        time.sleep(5)
        s = requests.get(f"https://api.x.ai/v1/videos/{req_id}", headers=headers, timeout=60).json()
        status = s.get("status")
        progress(f"AI video: {status} ({(i + 1) * 5}s)")
        if status == "done":
            out.write_bytes(requests.get(s["video"]["url"], timeout=300).content)
            return
        if status in ("failed", "expired"):
            raise RuntimeError(f"xAI video generation {status}: {s}")
    raise TimeoutError("xAI video took too long.")


def _openai_video(prompt: str, secs: int, out: Path, start_image: Path | None, progress) -> None:
    client = openai_client()
    secs = min((4, 8, 12), key=lambda s: abs(s - secs))
    kwargs = dict(model=config.VIDEO_MODEL, prompt=prompt, seconds=str(secs), size="720x1280")
    if start_image:
        kwargs["input_reference"] = open(start_image, "rb")
    job = client.videos.create(**kwargs)
    while job.status in ("queued", "in_progress"):
        time.sleep(6)
        job = client.videos.retrieve(job.id)
        progress(f"AI video: {job.status} {getattr(job, 'progress', '')}%")
    if job.status != "completed":
        raise RuntimeError(f"OpenAI video failed: {job}")
    client.videos.download_content(job.id, variant="video").write_to_file(out)


# ---- free stock footage ---------------------------------------------------------------

def stock_video(query: str, out_dir: Path, min_seconds: float = 3, skip: int = 0) -> Path | None:
    """`skip` = how many matching clips to pass over (to swap a clip the quality check rejected)."""
    if not config.PEXELS_API_KEY:
        return None
    out = out_dir / (f"stock_{_key(query)}.mp4" if not skip else f"stock_{_key(query, skip)}.mp4")
    if out.exists():
        return out
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": config.PEXELS_API_KEY},
                     params={"query": query, "orientation": "portrait", "per_page": 8, "size": "medium"},
                     timeout=30)
    r.raise_for_status()
    for v in r.json().get("videos", []):
        if v.get("duration", 0) < min_seconds:
            continue
        files = [f for f in v["video_files"] if f.get("height") and f["height"] >= f.get("width", 0)
                 and f["height"] >= 1280 and f.get("file_type") == "video/mp4"]
        if not files:
            continue
        if skip:
            skip -= 1
            continue
        best = min(files, key=lambda f: abs(f["height"] - 1920))
        out.write_bytes(requests.get(best["link"], timeout=300).content)
        return out
    return None


def fit_image(src: Path, out: Path) -> Path:
    """Crop/resize any image to 1080x1920."""
    img = bk.cover_fit(Image.open(src).convert("RGB"), config.W, config.H)
    img.save(out)
    return out

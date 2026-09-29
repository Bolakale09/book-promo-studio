"""Brand kit: one look for every video - handle, logo watermark, colour, caption font, standing hashtags and
call-to-action. Stored once (not per book), so every book shares the same author brand."""
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import book as bk, config

BRAND_DIR = config.DATA / "brand"
FILE = BRAND_DIR / "brand.json"
FONTS = ["", "Arial Black", "Georgia", "Arial", "Comic Sans MS"]      # "" = follow the book's genre
FONT_LABEL = {"": "Follow the genre", "Arial Black": "Bold sans", "Georgia": "Classic serif", "Arial": "Clean sans",
              "Comic Sans MS": "Playful"}
POSITIONS = ["Top left", "Top right", "Bottom"]
DEFAULTS = {"name": "", "handle": "", "accent": "", "font": "", "watermark": True, "position": "Top left",
            "logo": "", "cta": "", "cta_on_end": False, "hashtags": [], "tagline": ""}
HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def load() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def save(data: dict) -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    clean = {k: data.get(k, DEFAULTS[k]) for k in DEFAULTS}
    clean["handle"] = clean["handle"].strip()
    if clean["handle"] and not clean["handle"].startswith("@"):
        clean["handle"] = "@" + clean["handle"]
    clean["accent"] = clean["accent"].strip()
    if clean["accent"] and not HEX.match(clean["accent"]):
        raise ValueError("Colour must look like #F0B429.")
    if clean["accent"] and not clean["accent"].startswith("#"):
        clean["accent"] = "#" + clean["accent"]
    clean["hashtags"] = hashtag_list(clean["hashtags"])
    FILE.write_text(json.dumps(clean, indent=1), encoding="utf-8")


def hashtag_list(x) -> list[str]:
    parts = re.split(r"[\s,]+", x) if isinstance(x, str) else list(x or [])
    out = []
    for p in parts:
        p = p.strip().lstrip("#")
        if p and re.fullmatch(r"\w+", p) and f"#{p}" not in out:
            out.append(f"#{p}")
    return out


def is_set(b: dict | None = None) -> bool:
    b = b or load()
    return bool(b["handle"] or b["logo"] or b["accent"] or b["font"] or b["cta"] or b["hashtags"])


def save_logo(data: bytes, filename: str) -> str:
    """Store the logo as a trimmed PNG so the watermark looks the same everywhere."""
    import io
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    if img.getbbox():
        img = img.crop(img.getbbox())
    img.thumbnail((600, 600))
    img.save(BRAND_DIR / "logo.png")
    return "logo.png"


def logo_path(b: dict | None = None) -> Path | None:
    b = b or load()
    p = BRAND_DIR / (b["logo"] or "logo.png")
    return p if b["logo"] and p.exists() else None


def remove_logo() -> None:
    (BRAND_DIR / "logo.png").unlink(missing_ok=True)
    save({**load(), "logo": ""})


def accent_rgb(genre_accent: tuple, b: dict | None = None) -> tuple:
    """Caption highlight colour: the brand colour if set, otherwise the genre's."""
    b = b or load()
    if b["accent"]:
        h = b["accent"].lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return genre_accent


def caption_font(genre_font: str, b: dict | None = None) -> str:
    b = b or load()
    return b["font"] or genre_font


def watermark(size: tuple, k: float = 1.0, b: dict | None = None) -> tuple[Image.Image, tuple] | None:
    """A small RGBA badge (logo + @handle) and where to paste it on a frame of `size`. None if not wanted."""
    b = b or load()
    if not b["watermark"] or not (b["handle"] or logo_path(b)):
        return None
    w, h = size
    fh = max(18, int(34 * k))
    fnt = bk.font(caption_font("Arial", b) if b["font"] else "Arial", fh)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    pad = int(14 * k)
    icon = None
    lp = logo_path(b)
    if lp:
        icon = Image.open(lp).convert("RGBA")
        ih = int(56 * k)
        icon = icon.resize((max(1, int(icon.width * ih / icon.height)), ih), Image.LANCZOS)
    tw = int(tmp.textlength(b["handle"], font=fnt)) if b["handle"] else 0
    gap = int(10 * k) if icon and tw else 0
    bw = pad * 2 + (icon.width if icon else 0) + gap + tw
    bh = pad * 2 + max(icon.height if icon else 0, fh + int(8 * k))
    badge = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(badge)
    d.rounded_rectangle((0, 0, bw - 1, bh - 1), radius=bh // 2 if not icon else int(18 * k), fill=(0, 0, 0, 105))
    x = pad
    if icon:
        badge.alpha_composite(icon, (x, (bh - icon.height) // 2))
        x += icon.width + gap
    if tw:
        d.text((x, bh / 2), b["handle"], font=fnt, fill=(255, 255, 255, 235), anchor="lm")
    margin = int(46 * k)
    pos = b["position"]
    if pos == "Top right":
        xy = (w - bw - margin, int(h * 0.062))
    elif pos == "Bottom":
        xy = ((w - bw) // 2, int(h * 0.905))
    else:
        xy = (margin, int(h * 0.062))
    return badge, xy


def merge_hashtags(script_tags: list[str], b: dict | None = None, limit: int = 8) -> list[str]:
    b = b or load()
    out = []
    for t in [*hashtag_list(script_tags), *b["hashtags"]]:
        if t.lower() not in [o.lower() for o in out]:
            out.append(t)
    return out[:limit]

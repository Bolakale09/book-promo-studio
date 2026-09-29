"""Book profile: details, cover, characters, manuscript pages and the AI 'digest' of the book."""
import json
import random
import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import config, llm
from .genres import GENRES

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts"), Path.home() / ".fonts"]

# Windows font first, then the free Linux look-alikes installed on the web server (see packages.txt)
FONT_FILES = {
    "serif": ["georgia.ttf", "times.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf"],
    "serif-italic": ["georgiai.ttf", "timesi.ttf", "LiberationSerif-Italic.ttf", "DejaVuSerif-Italic.ttf"],
    "bold": ["ariblk.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
    "sans": ["arial.ttf", "segoeui.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"],
    "Georgia": ["georgiab.ttf", "georgia.ttf", "LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf"],
    "Arial Black": ["ariblk.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
    "Arial": ["arialbd.ttf", "arial.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "Comic Sans MS": ["comicbd.ttf", "comic.ttf", "ComicNeue-Bold.ttf", "ComicNeue-Bold.otf",
                      "DejaVuSans-Bold.ttf"],
}
_font_paths: dict[str, Path | None] = {}


def _find_font(filename: str) -> Path | None:
    if filename not in _font_paths:
        _font_paths[filename] = None
        for d in FONT_DIRS:
            if (d / filename).exists():
                _font_paths[filename] = d / filename
                break
            if d.exists() and d.name != "Fonts":  # Linux keeps fonts in sub-folders
                hit = next(d.rglob(filename), None)
                if hit:
                    _font_paths[filename] = hit
                    break
    return _font_paths[filename]


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for f in FONT_FILES.get(name, FONT_FILES["bold"]):
        p = _find_font(f)
        if p:
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


# ---- storage ----------------------------------------------------------------

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "book"


def book_dir(book_id: str) -> Path:
    d = config.BOOKS_DIR / book_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_books() -> dict[str, dict]:
    return {p.parent.name: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(config.BOOKS_DIR.glob("*/book.json"))}


def load(book_id: str) -> dict:
    return json.loads((book_dir(book_id) / "book.json").read_text(encoding="utf-8"))


def save(book: dict) -> None:
    (book_dir(book["id"]) / "book.json").write_text(json.dumps(book, indent=1), encoding="utf-8")


def new_book(title: str) -> dict:
    return {"id": slug(title), "title": title, "author": "", "genre": "fiction", "blurb": "", "audience": "",
            "where_to_buy": "Amazon", "link": "", "cover": None, "manuscript": None, "characters": [],
            "digest": None, "background": None}


def path(book: dict, key: str) -> Path | None:
    name = book.get(key)
    return book_dir(book["id"]) / name if name else None


# ---- manuscript -> pages ------------------------------------------------------

WORDS_PER_PAGE = 230


def pages(book: dict) -> list[dict]:
    """[{page, text}], cached in pages.json."""
    ms = path(book, "manuscript")
    if not ms or not ms.exists():
        return []
    cache = book_dir(book["id"]) / "pages.json"
    if cache.exists() and cache.stat().st_mtime > ms.stat().st_mtime:
        return json.loads(cache.read_text(encoding="utf-8"))

    ext = ms.suffix.lower()
    if ext == ".pdf":
        import fitz
        with fitz.open(ms) as doc:
            out = [{"page": i + 1, "text": p.get_text().strip()} for i, p in enumerate(doc)]
    else:
        if ext == ".docx":
            import docx
            paras = [p.text.strip() for p in docx.Document(str(ms)).paragraphs]
        else:
            paras = [p.strip() for p in ms.read_text(encoding="utf-8", errors="replace").split("\n")]
        out, cur, count = [], [], 0
        for para in paras:
            n = len(para.split())
            if cur and count + n > WORDS_PER_PAGE:
                out.append({"page": len(out) + 1, "text": "\n".join(cur)})
                cur, count = [], 0
            cur.append(para)
            count += n
        if any(cur):
            out.append({"page": len(out) + 1, "text": "\n".join(cur)})
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out


def find_quote_page(book: dict, quote: str, hint: int | None = None) -> int | None:
    """Page number that contains `quote` (fuzzy), preferring the hinted page."""
    key = _normtext(quote)[:60]
    if not key:
        return hint
    all_pages = pages(book)
    order = sorted(all_pages, key=lambda p: abs(p["page"] - (hint or 0)))
    for p in order:
        if key in _normtext(p["text"]):
            return p["page"]
    return hint


def _normtext(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ---- AI digest of the book ------------------------------------------------------

DIGEST_SYSTEM = """You are a book marketing strategist for TikTok/Reels. You read manuscripts and find what will
make strangers FEEL something in 3 seconds. Quotes must be copied VERBATIM from the page text given, with the
correct page number. Respond with JSON only."""


def build_digest(book: dict, max_chars: int = 120_000) -> dict:
    pgs = [p for p in pages(book) if p["text"].strip()]
    if not pgs:
        raise RuntimeError("Upload the manuscript first.")
    total = sum(len(p["text"]) for p in pgs)
    if total > max_chars:  # sample evenly through the book to stay cheap
        keep = max(1, int(len(pgs) * max_chars / total))
        step = len(pgs) / keep
        pgs = [pgs[int(i * step)] for i in range(keep)]
    text = "\n\n".join(f"[[PAGE {p['page']}]]\n{p['text']}" for p in pgs)[:max_chars]
    g = GENRES[book["genre"]]

    user = f"""Book: "{book['title']}" by {book.get('author') or 'the author'}
Genre: {g['label']}
Author's blurb: {book.get('blurb') or '-'}
Intended audience: {book.get('audience') or '-'}

MANUSCRIPT (page markers like [[PAGE 12]]):
{text}

Return JSON:
{{
  "summary": "3-4 sentences, no spoilers",
  "emotional_promise": "the feeling a reader gets",
  "target_readers": ["specific identities who would love this (e.g. 'dads who struggle to say I love you')"],
  "themes": ["..."],
  "tropes_or_hooks": ["genre tropes / angles this book can be sold on"],
  "comparable_books": ["well-known similar titles"],
  "characters": [{{"name": "...", "description": "appearance + personality as written"}}],
  "quotes": [{{"page": 12, "text": "verbatim 1-3 sentence line that would stop a scroll", "why": "..."}}],
  "visual_world": "settings, colours, era, mood to show on screen"
}}
Give 12-20 quotes spread across the book, the most emotional / surprising / useful lines."""
    digest = llm.chat_json(DIGEST_SYSTEM, user, max_out=7000, what="book digest")
    for q in digest.get("quotes", []):  # make sure the page numbers are right
        q["page"] = find_quote_page(book, q.get("text", ""), q.get("page"))
    book["digest"] = digest
    fresh = load(book["id"])  # this can take a minute: keep any edits made in the meantime
    fresh["digest"] = digest
    save(fresh)
    return digest


def delete_book(book_id: str) -> None:
    """Remove a book with its scripts and videos, here and in cloud storage."""
    import shutil
    from . import storage
    for d in (config.BOOKS_DIR / book_id, config.PROJECTS_DIR / book_id):
        if d.exists():
            shutil.rmtree(d)
        storage.delete_remote_folder(d)


# ---- page images (the "page-to-page" shots) ------------------------------------

PAPER = (247, 241, 227)
INK = (38, 34, 30)
HIGHLIGHT = (255, 222, 90)


def render_page(book: dict, page_no: int, highlight: str = "") -> tuple[Image.Image, list[tuple]]:
    """Render one manuscript page as a clean image.
    Returns (image, boxes) where boxes are the pixel rectangles of the `highlight` words, in reading order."""
    ms = path(book, "manuscript")
    if ms and ms.suffix.lower() == ".pdf":
        return _render_pdf_page(ms, page_no, highlight)
    pg = next((p for p in pages(book) if p["page"] == page_no), None)
    return _render_text_page(pg["text"] if pg else "", page_no, highlight, book.get("title", ""))


def apply_highlight(img: Image.Image, boxes: list[tuple], progress: float = 1.0) -> Image.Image:
    """Highlighter-pen effect (multiplied, so the ink stays dark). `progress` 0-1 sweeps it on word by word."""
    if not boxes or progress <= 0:
        return img
    layer = Image.new("RGB", img.size, (255, 255, 255))
    d = ImageDraw.Draw(layer)
    total = sum(b[2] - b[0] for b in boxes)
    left = total * min(1.0, progress)
    for x0, y0, x1, y1 in boxes:
        if left <= 0:
            break
        w = min(x1 - x0, left)
        d.rounded_rectangle((x0, y0, x0 + w, y1), radius=6, fill=HIGHLIGHT)
        left -= x1 - x0
    from PIL import ImageChops
    return ImageChops.multiply(img.convert("RGB"), layer)


def highlight_focus(img: Image.Image, boxes: list[tuple]) -> tuple[float, float]:
    """Centre of the highlight as fractions 0-1 of the page (where the camera should push in)."""
    if not boxes:
        return 0.5, 0.42
    cx = sum((b[0] + b[2]) / 2 for b in boxes) / len(boxes) / img.width
    cy = sum((b[1] + b[3]) / 2 for b in boxes) / len(boxes) / img.height
    return cx, cy


def preview_page(book: dict, page_no: int, highlight: str = "") -> Image.Image:
    img, boxes = render_page(book, page_no, highlight)
    return apply_highlight(img, boxes, 1.0)


def page_count(book: dict) -> int:
    ms = path(book, "manuscript")
    if ms and ms.suffix.lower() == ".pdf" and ms.exists():
        import fitz
        with fitz.open(ms) as doc:
            return len(doc)
    return len(pages(book))


def _render_pdf_page(ms: Path, page_no: int, highlight: str):
    import fitz
    with fitz.open(ms) as doc:
        page = doc[max(0, min(page_no - 1, len(doc) - 1))]
        rects = []
        if highlight:
            words = highlight.split()
            for probe in (highlight, " ".join(words[:8]), " ".join(words[:4])):
                rects = page.search_for(probe) if probe else []
                if rects:
                    break
        zoom = 1100 / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        from PIL import ImageChops  # warm paper tone + grain so it looks printed, not on-screen
        img = ImageChops.multiply(img, Image.new("RGB", img.size, (250, 245, 233)))
        img = Image.blend(img, Image.effect_noise(img.size, 9).convert("RGB"), 0.04)
        boxes = [(r.x0 * zoom - 3, r.y0 * zoom - 2, r.x1 * zoom + 3, r.y1 * zoom + 2) for r in rects]
        return img, boxes


def _render_text_page(text: str, page_no: int, highlight: str, title: str):
    Wp, Hp, margin = 1000, 1414, 95
    img = Image.new("RGB", (Wp, Hp), PAPER)
    grain = Image.effect_noise((Wp, Hp), 9).convert("RGB")  # subtle paper grain
    img = Image.blend(img, grain, 0.05)
    d = ImageDraw.Draw(img)

    f, fh = font("serif", 33), font("serif-italic", 24)
    d.text((Wp / 2, 55), title[:60], font=fh, fill=(120, 110, 100), anchor="mm")
    d.text((Wp / 2, Hp - 60), str(page_no), font=fh, fill=(120, 110, 100), anchor="mm")

    hl_words = set()
    words_all = text.split()
    if highlight:
        target = [_normtext(w) for w in highlight.split() if _normtext(w)]
        norm = [_normtext(w) for w in words_all]
        for i in range(len(norm)):
            if target and norm[i:i + len(target)] == target:
                hl_words = set(range(i, i + len(target)))
                break
        if not hl_words and target:  # partial: first 5 words
            t5 = target[:5]
            for i in range(len(norm)):
                if norm[i:i + len(t5)] == t5:
                    hl_words = set(range(i, min(len(norm), i + len(target))))
                    break

    y, line_h, idx, boxes = 120, 50, 0, []
    space = d.textlength(" ", font=f)
    for para in text.split("\n"):
        for line in textwrap.wrap(para, width=48) or [""]:
            if y > Hp - 120:
                break
            x = margin
            for w in line.split():
                wl = d.textlength(w, font=f)
                if idx in hl_words:
                    last = idx + 1 not in hl_words
                    boxes.append((x - 4, y - 4, x + wl + (0 if last else space), y + line_h - 8))
                d.text((x, y), w, font=f, fill=INK)
                x += wl + space
                idx += 1
            y += line_h
        y += 14
    return img, boxes


# ---- compositing into realistic 9:16 frames -----------------------------------------

def background(book: dict) -> Image.Image:
    """Desk/table photo behind pages and cover. Uses the AI background if generated, else a warm gradient."""
    bg = path(book, "background")
    if bg and bg.exists():
        return cover_fit(Image.open(bg).convert("RGB"), config.W, config.H)
    img = Image.new("RGB", (config.W, config.H))
    d = ImageDraw.Draw(img)
    for yy in range(config.H):  # warm wood-ish vertical gradient
        t = yy / config.H
        d.line([(0, yy), (config.W, yy)], fill=(int(70 - 30 * t), int(48 - 22 * t), int(34 - 18 * t)))
    grain = Image.effect_noise((config.W, config.H), 30).convert("RGB")
    return Image.blend(img, grain, 0.08)


def cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s + 0.5), int(img.height * s + 0.5)), Image.LANCZOS)
    l, t = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((l, t, l + w, t + h))


def paste_with_shadow(base: Image.Image, item: Image.Image, center: tuple[int, int], angle: float) -> Image.Image:
    item = item.convert("RGBA").rotate(angle, resample=Image.BICUBIC, expand=True)
    shadow = Image.new("RGBA", item.size, (0, 0, 0, 0))
    shadow.putalpha(item.split()[3].point(lambda a: int(a * 0.55)))
    pad = 60
    sh = Image.new("RGBA", (item.width + pad * 2, item.height + pad * 2), (0, 0, 0, 0))
    sh.paste(shadow, (pad, pad))
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    base = base.convert("RGBA")
    x, y = center[0] - item.width // 2, center[1] - item.height // 2
    base.alpha_composite(sh, (max(0, x - pad + 18), max(0, y - pad + 26)))
    base.alpha_composite(item, (max(0, x), max(0, y)))
    return base.convert("RGB")


def vignette(img: Image.Image) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((-250, -150, img.width + 250, img.height + 150), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(180))
    dark = Image.new("RGB", img.size, (0, 0, 0))
    return Image.composite(img, dark, mask)


def cover_image(book: dict) -> Image.Image:
    """The front cover as uploaded, or a clean title cover if there is none."""
    cov = path(book, "cover")
    if cov and cov.exists():
        return Image.open(cov).convert("RGB")
    cover = Image.new("RGB", (600, 900), (40, 50, 70))
    d = ImageDraw.Draw(cover)
    for y in range(900):
        d.line([(0, y), (600, y)], fill=(36 + y // 60, 46 + y // 55, 70 + y // 40))
    d.multiline_text((300, 430), textwrap.fill(book.get("title", ""), 14), font=font("Georgia", 58),
                     fill=(245, 236, 215), anchor="mm", align="center", spacing=14)
    if book.get("author"):
        d.text((300, 800), book["author"], font=font("serif", 30), fill=(230, 200, 140), anchor="mm")
    return cover


def book_object(book: dict, width: int = 700) -> Image.Image:
    """3D-looking book (RGBA): page block, spine shading and gloss. Place it on the desk with paste_with_shadow."""
    cov = path(book, "cover")
    if cov and cov.exists():
        cover = Image.open(cov).convert("RGB")
    else:
        cover = Image.new("RGB", (600, 900), (40, 50, 70))
        d = ImageDraw.Draw(cover)
        d.multiline_text((300, 450), textwrap.fill(book.get("title", ""), 14), font=font("bold", 56),
                         fill="white", anchor="mm", align="center")
    cover = cover.resize((width, int(cover.height * width / cover.width)), Image.LANCZOS)
    depth = 26
    book_img = Image.new("RGBA", (cover.width + depth, cover.height + depth), (0, 0, 0, 0))
    d = ImageDraw.Draw(book_img)
    for i in range(depth, 0, -2):  # stacked page edges
        shade = 235 - (i % 4) * 8
        d.rectangle((i, i, cover.width + i - 1, cover.height + i - 1), fill=(shade, shade - 6, shade - 16, 255))
    cover = cover.convert("RGBA")
    spine = Image.new("RGBA", (40, cover.height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(spine)
    for x in range(40):
        sd.line([(x, 0), (x, cover.height)], fill=(0, 0, 0, int(110 * (1 - x / 40))))
    cover.alpha_composite(spine, (0, 0))
    gloss = Image.new("RGBA", cover.size, (0, 0, 0, 0))
    ImageDraw.Draw(gloss).polygon([(0, 0), (cover.width * 0.55, 0), (0, cover.height * 0.45)],
                                  fill=(255, 255, 255, 28))
    cover.alpha_composite(gloss)
    book_img.alpha_composite(cover, (0, 0))
    return book_img


def cover_thumb(book: dict, width: int = 420) -> Image.Image | None:
    cov = path(book, "cover")
    if not cov or not cov.exists():
        return None
    im = Image.open(cov).convert("RGB")
    return im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)

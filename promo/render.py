"""Assemble a script variant into a finished 9:16 MP4.

Manuscript pages turn and get highlighted, the book drops onto the desk, AI / stock footage plays, the narrator
speaks, captions pop word by word and music sits underneath. Frames are drawn with Pillow and piped into FFmpeg,
so no special FFmpeg build (libass etc.) is needed.
"""
import json
import math
import os
import random
import re
import subprocess
import tempfile
import threading
import wave
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import book as bk, budget, config, ffmpeg_utils as ff, visuals, voice
from .genres import GENRES
from .transcribe import align_words

W, H, FPS = config.W, config.H, config.FPS
S = 1.5                      # desk scenes are composed larger than the output so the camera can push in sharply
CW, CH = int(W * S), int(H * S)
LEAD, TAIL = 0.15, 0.35      # silence before / after each block of narration
SILENT_DEFAULT = 3.0
LAST_SCENE_MIN = 2.8         # the breadcrumb needs time to be read

AI_VISUALS = ("character", "ai_image", "ai_video")


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def ease_out(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 1 - (1 - u) ** 3


def ass_to_rgb(c: str) -> tuple[int, int, int]:
    """Genre accents are stored ASS-style (&HAABBGGRR)."""
    h = c.replace("&H", "").rjust(8, "0")
    return int(h[6:8], 16), int(h[4:6], 16), int(h[2:4], 16)


def seed_for(*parts) -> int:
    return zlib.crc32("|".join(map(str, parts)).encode())


# ---- drawing helpers -------------------------------------------------------------------

def camera(canvas: Image.Image, zoom: float, cx: float, cy: float, t: float = 0.0, shake: float = 1.0) -> Image.Image:
    """Crop a W:H window of `canvas` (zoom 1 = everything) centred near (cx, cy), with a faint hand-held drift."""
    bw, bh = canvas.width / zoom, canvas.height / zoom
    x0 = cx - bw / 2 + shake * 2.5 * S * math.sin(t * 1.9)
    y0 = cy - bh / 2 + shake * 2.5 * S * math.cos(t * 1.4)
    x0 = min(max(x0, 0.0), canvas.width - bw)
    y0 = min(max(y0, 0.0), canvas.height - bh)
    return canvas.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + bw, y0 + bh))


def rot(px: float, py: float, angle: float, pc: tuple, cc: tuple) -> tuple[float, float]:
    """Point in page space -> canvas, for a page rotated by `angle` (PIL convention) around pc placed at cc."""
    a = math.radians(angle)
    dx, dy = px - pc[0], py - pc[1]
    return cc[0] + dx * math.cos(a) + dy * math.sin(a), cc[1] - dx * math.sin(a) + dy * math.cos(a)


def place(canvas: Image.Image, img: Image.Image, angle: float, center: tuple) -> None:
    rgba = img.convert("RGBA").rotate(angle, resample=Image.BICUBIC, expand=True)
    canvas.paste(rgba, (round(center[0] - rgba.width / 2), round(center[1] - rgba.height / 2)), rgba)


def soft_shadow(size: tuple, angle: float, blur: float = 26 * S, strength: float = 0.55) -> Image.Image:
    w, h = size
    pad = int(blur * 3)
    m = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(m).rectangle((pad, pad, pad + w, pad + h), fill=int(255 * strength))
    return m.rotate(angle, resample=Image.BICUBIC, expand=True).filter(ImageFilter.GaussianBlur(blur))


def darken(canvas: Image.Image, mask: Image.Image, center: tuple) -> None:
    x, y = round(center[0] - mask.width / 2), round(center[1] - mask.height / 2)
    canvas.paste(Image.new("RGB", mask.size, (0, 0, 0)), (x, y), mask)


def persp_coeffs(dst: list, src: list) -> list:
    """PIL PERSPECTIVE data that maps output quad `dst` onto source quad `src`."""
    a, b = [], []
    for (x, y), (X, Y) in zip(dst, src):
        a.append([x, y, 1, 0, 0, 0, -X * x, -X * y])
        b.append(X)
        a.append([0, 0, 0, x, y, 1, -Y * x, -Y * y])
        b.append(Y)
    return np.linalg.solve(np.array(a, float), np.array(b, float)).tolist()


def desk_canvas(book: dict) -> Image.Image:
    return bk.vignette(bk.background(book).resize((CW, CH), Image.LANCZOS))


# ---- scenes (each returns a W x H frame for local time t) ---------------------------------

class PageScene:
    """A page of the manuscript lying open on the desk. Earlier pages turn over first ("page to page"),
    then the quote is swept with a highlighter while the camera pushes in on it."""

    def __init__(self, book: dict, desk: Image.Image, page_no: int, highlight: str, dur: float, flips: int, seed: int):
        rnd = random.Random(seed)
        self.dur = dur
        n_pages = max(1, bk.page_count(book))
        page_no = max(1, min(page_no, n_pages))
        tgt, boxes = bk.render_page(book, page_no, highlight)
        pw = int(CW * 0.84)
        sc = pw / tgt.width
        if tgt.height * sc > CH * 0.86:
            sc = CH * 0.86 / tgt.height
            pw = int(tgt.width * sc)
        ph = int(tgt.height * sc)
        self.pw, self.ph = pw, ph
        self.target = tgt.resize((pw, ph), Image.LANCZOS)
        self.boxes = [tuple(v * sc for v in b) for b in boxes]

        first = max(1, page_no - max(0, flips))
        self.prev = [self._page(book, p) for p in range(first, page_no)]
        self.backs = [self._back(p) for p in self.prev]
        self.initial_left = self._back(self._page(book, first - 1)) if first > 1 else None
        self.prev_rgba = [p.convert("RGBA") for p in self.prev]
        self.backs_rgba = [b.convert("RGBA") for b in self.backs]

        self.angle = rnd.uniform(-1.8, 1.8)
        self.cc = (CW / 2, CH * 0.5)
        self.pc = (pw / 2, ph / 2)
        self.desk = desk.copy()
        darken(self.desk, soft_shadow((pw, ph), self.angle), (self.cc[0] + 16 * S, self.cc[1] + 24 * S))
        self.gutter = self._gutter()

        n = len(self.prev)
        self.hold = 0.25 if n else 0.0
        self.turn = (0.65 if n == 1 else 0.34) if n else 0.0
        if n and self.hold + n * self.turn > dur * 0.5:
            self.turn = max(0.2, (dur * 0.5 - self.hold) / n)
        self.flip_end = self.hold + n * self.turn
        self.flip_times = [self.hold + i * self.turn for i in range(n)]
        self.hl_start = self.flip_end + 0.15
        self.hl_dur = min(1.2, max(0.5, 0.1 * len(self.boxes)))
        fx, fy = bk.highlight_focus(self.target, self.boxes) if self.boxes else (0.5, 0.36)
        self.focus = rot(fx * pw, fy * ph, self.angle, self.pc, self.cc)
        self.zoom_end = 1.2
        if self.boxes:  # push in close, but keep the whole highlighted passage in frame
            xs = [x for b in self.boxes for x in (b[0], b[2])]
            ys = [y for b in self.boxes for y in (b[1], b[3])]
            self.zoom_end = max(1.1, min(1.5, CW * 0.88 / max(1, max(xs) - min(xs)), CH * 0.5 / max(1, max(ys) - min(ys))))
        self._cache: dict = {}
        self._hl_polys = [[rot(x, y, self.angle, self.pc, self.cc) for x, y in ((b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3]))]
                          for b in self.boxes]

    def _page(self, book: dict, no: int) -> Image.Image:
        return bk.render_page(book, no)[0].resize((self.pw, self.ph), Image.LANCZOS)

    def _back(self, img: Image.Image) -> Image.Image:
        """Back of a sheet: paper with the other side's text faintly showing through."""
        paper = Image.new("RGB", img.size, bk.PAPER)
        return Image.blend(paper, ImageOps.mirror(img), 0.07)

    def _gutter(self) -> Image.Image:
        g = int(self.pw * 0.07)
        band = Image.new("L", (2 * g, self.ph), 0)
        d = ImageDraw.Draw(band)
        for x in range(2 * g):
            d.line([(x, 0), (x, self.ph)], fill=int(120 * (1 - abs(x - g) / g) ** 2))
        return band.rotate(self.angle, resample=Image.BICUBIC, expand=True)

    def _canvas(self, top: Image.Image, left: Image.Image | None, hl: float = 0.0) -> Image.Image:
        key = (id(top), id(left), hl)
        if key in self._cache:
            return self._cache[key]
        if 0 < hl < 1:
            c = self._partial(self._canvas(top, left, 0.0), self._canvas(top, left, 1.0), hl)
        else:
            c = self.desk.copy()
            if left is not None:
                place(c, left, self.angle, rot(-self.pw / 2, self.ph / 2, self.angle, self.pc, self.cc))
            place(c, bk.apply_highlight(top, self.boxes, 1.0) if hl >= 1 else top, self.angle, self.cc)
            if left is not None:
                darken(c, self.gutter, rot(0, self.ph / 2, self.angle, self.pc, self.cc))
        if len(self._cache) > 6:
            self._cache = {k: v for k, v in self._cache.items() if k[2] in (0.0, 1.0)}
        self._cache[key] = c
        return c

    def _partial(self, clean: Image.Image, full: Image.Image, hl: float) -> Image.Image:
        """Highlighter part-way across the quote: reveal the fully-highlighted canvas box by box."""
        xs = [x for poly in self._hl_polys for x, _ in poly]
        ys = [y for poly in self._hl_polys for _, y in poly]
        bx0, by0, bx1, by1 = int(min(xs)) - 4, int(min(ys)) - 4, int(max(xs)) + 5, int(max(ys)) + 5
        mask = Image.new("L", (bx1 - bx0, by1 - by0), 0)
        d = ImageDraw.Draw(mask)
        total = sum(b[2] - b[0] for b in self.boxes)
        left = total * hl
        for b, poly in zip(self.boxes, self._hl_polys):
            if left <= 0:
                break
            f = min(1.0, left / max(1e-6, b[2] - b[0]))
            (ax, ay), (bxx, byy), (cx_, cy_), (dx, dy) = poly
            d.polygon([(ax - bx0, ay - by0), (ax + (bxx - ax) * f - bx0, ay + (byy - ay) * f - by0),
                       (dx + (cx_ - dx) * f - bx0, dy + (cy_ - dy) * f - by0), (dx - bx0, dy - by0)], fill=255)
            left -= b[2] - b[0]
        c = clean.copy()
        c.paste(full.crop((bx0, by0, bx1, by1)), (bx0, by0), mask)
        return c

    def _turning(self, c: Image.Image, i: int, u: float) -> None:
        """Draw sheet i part-way through turning over the spine (u 0 -> 1)."""
        th = math.pi * u
        cs, sn = math.cos(th), math.sin(th)
        if abs(cs) < 0.03:
            return
        pw, ph, k = self.pw, self.ph, 0.06
        ex = pw * cs
        quad = [(0, 0), (ex, -ph * k * sn), (ex, ph + ph * k * sn), (0, ph)]
        pts = [rot(x, y, self.angle, self.pc, self.cc) for x, y in quad]
        if cs > 0:
            img, src, shade = self.prev_rgba[i], [(0, 0), (pw, 0), (pw, ph), (0, ph)], 0.3 * sn * sn
        else:
            img, src, shade = self.backs_rgba[i], [(pw, 0), (0, 0), (0, ph), (pw, ph)], 0.22 * sn

        # shadow the lifted sheet casts on the page underneath
        sx = ex + math.copysign(pw * 0.12 * sn, cs)
        sh_pts = [rot(x, y, self.angle, self.pc, self.cc) for x, y in [(0, 0), (sx, 0), (sx, ph), (0, ph)]]
        mx0, my0 = min(p[0] for p in sh_pts) - 60, min(p[1] for p in sh_pts) - 60
        mw, mh = int(max(p[0] for p in sh_pts) - mx0 + 60), int(max(p[1] for p in sh_pts) - my0 + 60)
        if mw > 8 and mh > 8:
            q = 4
            m = Image.new("L", (mw // q, mh // q), 0)
            ImageDraw.Draw(m).polygon([((x - mx0) / q, (y - my0) / q) for x, y in sh_pts], fill=int(120 * sn))
            m = m.filter(ImageFilter.GaussianBlur(14 * S / q)).resize((mw, mh), Image.BILINEAR)
            c.paste((0, 0, 0), (int(mx0), int(my0), int(mx0) + mw, int(my0) + mh), m)

        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, y0 = math.floor(min(xs)), math.floor(min(ys))
        bw, bh = math.ceil(max(xs)) - x0, math.ceil(max(ys)) - y0
        if bw < 2 or bh < 2:
            return
        piece = img.transform((bw, bh), Image.PERSPECTIVE, persp_coeffs([(x - x0, y - y0) for x, y in pts], src),
                              Image.BILINEAR)
        alpha = piece.split()[3]
        f = 1 - shade
        rgb = piece.convert("RGB").point(lambda v: int(v * f))
        c.paste(rgb, (x0, y0), alpha)

    def frame(self, t: float) -> Image.Image:
        n = len(self.prev)
        if n and t < self.flip_end:
            i = 0 if t < self.hold else min(n - 1, int((t - self.hold) // self.turn))
            u = 0.0 if t < self.hold else ease((t - self.hold - i * self.turn) / self.turn)
            beneath = self.prev[i + 1] if i + 1 < n else self.target
            left = self.backs[i - 1] if i > 0 else self.initial_left
            c = self._canvas(beneath, left).copy()
            self._turning(c, i, u)
            return camera(c, 1.03, self.cc[0], self.cc[1], t)
        left = self.backs[-1] if n else self.initial_left
        hl = round(ease((t - self.hl_start) / self.hl_dur) * 16) / 16 if self.boxes else 0.0
        c = self._canvas(self.target, left, hl)
        u = ease((t - self.flip_end) / max(0.4, self.dur - self.flip_end - 0.1))
        zoom = 1.03 + (self.zoom_end - 1.03) * u
        cx = self.cc[0] + (self.focus[0] - self.cc[0]) * u
        cy = self.cc[1] + (self.focus[1] - self.cc[1]) * u
        return camera(c, zoom, cx, cy, t)


class CoverScene:
    """The physical book slides onto the desk, a light glints across the cover, the camera eases in."""

    def __init__(self, book: dict, desk: Image.Image, dur: float, seed: int):
        self.dur = dur
        self.angle = random.Random(seed).uniform(-4, -2)
        obj = bk.book_object(book, width=int(CW * 0.6))
        self.obj = obj.rotate(self.angle, resample=Image.BICUBIC, expand=True)
        self.shadow = soft_shadow(obj.size, self.angle, blur=30 * S, strength=0.65)
        self.desk = desk
        self.rest = (CW / 2, CH * 0.5)
        self.static = None
        self.slide = min(0.6, dur * 0.25)

    def _compose(self, cy: float) -> Image.Image:
        c = self.desk.copy()
        darken(c, self.shadow, (self.rest[0] + 22 * S, cy + 34 * S))
        c.paste(self.obj, (round(self.rest[0] - self.obj.width / 2), round(cy - self.obj.height / 2)), self.obj)
        return c

    def _glint(self, c: Image.Image, u: float) -> Image.Image:
        w, h = self.obj.size
        q = 4
        band = Image.new("L", (w // q, h // q), 0)
        x = (-w * 0.6 + u * w * 2.2) / q
        ImageDraw.Draw(band).polygon([(x, 0), (x + w * 0.22 / q, 0), (x - w * 0.3 / q, h / q), (x - w * 0.52 / q, h / q)],
                                     fill=70)
        band = band.filter(ImageFilter.GaussianBlur(25 * S / q)).resize((w, h), Image.BILINEAR)
        from PIL import ImageChops
        band = ImageChops.multiply(band, self.obj.split()[3])
        c = c.copy()
        c.paste(Image.new("RGB", band.size, (255, 255, 255)),
                (round(self.rest[0] - w / 2), round(self.rest[1] - h / 2)), band)
        return c

    def frame(self, t: float) -> Image.Image:
        u = ease_out(t / self.slide) if self.slide > 0 else 1.0
        if u < 1:
            c = self._compose(self.rest[1] + (1 - u) * CH * 0.75)
        else:
            if self.static is None:
                self.static = self._compose(self.rest[1])
            c = self.static
            g0 = self.slide + 0.3
            if g0 <= t <= g0 + 0.9:
                c = self._glint(c, (t - g0) / 0.9)
        z = 1.02 + 0.1 * ease((t - self.slide) / max(0.5, self.dur - self.slide))
        return camera(c, z, self.rest[0], self.rest[1], t)


class StillScene:
    """AI photo with a slow, realistic camera move (Ken Burns)."""

    def __init__(self, img_path: Path, dur: float, seed: int):
        rnd = random.Random(seed)
        self.dur = dur
        self.c = bk.cover_fit(Image.open(img_path).convert("RGB"), CW, CH)
        self.z0, self.z1 = (1.02, 1.16) if rnd.random() < 0.7 else (1.16, 1.02)
        self.p0 = (CW * rnd.uniform(0.44, 0.56), CH * rnd.uniform(0.42, 0.52))
        self.p1 = (CW * rnd.uniform(0.44, 0.56), CH * rnd.uniform(0.42, 0.52))

    def frame(self, t: float) -> Image.Image:
        u = min(1.0, t / max(0.1, self.dur))
        return camera(self.c, self.z0 + (self.z1 - self.z0) * u, self.p0[0] + (self.p1[0] - self.p0[0]) * u,
                      self.p0[1] + (self.p1[1] - self.p0[1]) * u, t, shake=0.6)


class VideoScene:
    """Real footage (stock, own B-roll or AI video), cropped to 9:16 and looped if it is too short."""

    def __init__(self, path: Path, dur: float):
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
        self.p = subprocess.Popen(
            [ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-stream_loop", "-1", "-i", str(path),
             "-t", f"{dur + 0.5:.2f}", "-vf", vf, "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.last = Image.new("RGB", (W, H))

    def frame(self, t: float) -> Image.Image:
        buf = self.p.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            self.last = Image.frombytes("RGB", (W, H), buf)
        return self.last.copy()

    def close(self) -> None:
        try:
            self.p.stdout.close()
            self.p.kill()
        except Exception:
            pass


# ---- text: on-screen overlay + word-by-word captions ------------------------------------------

def _wrap(draw: ImageDraw.ImageDraw, words: list[str], fnt, max_w: float) -> list[list[int]]:
    """Indices of words per line."""
    lines, cur = [], []
    for i, w in enumerate(words):
        test = " ".join(words[j] for j in cur + [i])
        if cur and draw.textlength(test, font=fnt) > max_w:
            lines.append(cur)
            cur = []
        cur.append(i)
    if cur:
        lines.append(cur)
    return lines


def text_card(text: str, font_name: str, size: int, style: str, max_w: int = 900) -> Image.Image:
    """'box' = black text on white rounded pills (classic TikTok hook), 'shadow' = white text with outline."""
    fnt = bk.font(font_name, size)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    words = text.split()
    lines = [" ".join(words[i] for i in ln) for ln in _wrap(tmp, words, fnt, max_w - size)]
    asc, desc = fnt.getmetrics()
    lh = asc + desc
    widths = [tmp.textlength(l, font=fnt) for l in lines]
    if style == "box":
        padx, pady = int(size * 0.42), int(size * 0.2)
        line_h = lh + 2 * pady
        img = Image.new("RGBA", (int(max(widths) + 2 * padx + 8), line_h * len(lines) + 8), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for i, w in enumerate(widths):
            x0 = (img.width - w) / 2 - padx
            d.rounded_rectangle((x0, i * line_h, x0 + w + 2 * padx, (i + 1) * line_h + 2),
                                radius=int(size * 0.3), fill=(255, 255, 255, 245))
        for i, l in enumerate(lines):
            d.text((img.width / 2, i * line_h + line_h / 2), l, font=fnt, fill=(18, 18, 18), anchor="mm")
        return img
    gap = int(size * 0.2)
    pad = int(size * 0.5)
    img = Image.new("RGBA", (int(max(widths) + 2 * pad), (lh + gap) * len(lines) + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(img), ImageDraw.Draw(shadow)
    sw = max(2, int(size * 0.06))
    for i, l in enumerate(lines):
        pos = (img.width / 2, pad + i * (lh + gap) + lh / 2)
        ds.text((pos[0], pos[1] + size * 0.06), l, font=fnt, fill=(0, 0, 0, 200), anchor="mm",
                stroke_width=sw * 2, stroke_fill=(0, 0, 0, 200))
        d.text(pos, l, font=fnt, fill=(255, 255, 255), anchor="mm", stroke_width=sw, stroke_fill=(10, 10, 10))
    shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.12))
    shadow.alpha_composite(img)
    return shadow


class Captions:
    """TikTok-style captions: 1-3 words at a time, the spoken word lit up in the genre accent colour."""

    def __init__(self, words: list[dict], font_name: str, accent: tuple, upper: bool):
        self.font = bk.font(font_name, 84 if font_name == "Georgia" else 78)
        self.accent, self.upper = accent, upper
        self.chunks = self._chunk(words)

    @staticmethod
    def _chunk(words: list[dict]) -> list[dict]:
        chunks, cur = [], []
        for k, w in enumerate(words):
            cur.append(w)
            nxt = words[k + 1] if k + 1 < len(words) else None
            text = " ".join(x["word"] for x in cur)
            if (nxt is None or len(cur) >= 3 or len(text) > 15 or re.search(r"[.,!?;:—]$", w["word"])
                    or nxt["scene"] != w["scene"] or nxt["start"] - w["end"] > 0.45):
                chunks.append({"words": cur, "start": cur[0]["start"], "end": cur[-1]["end"] + 0.25})
                cur = []
        for a, b in zip(chunks, chunks[1:]):
            a["end"] = min(max(a["end"], a["words"][-1]["end"]), b["start"])
        return chunks

    def for_scene(self, scene: int) -> "SceneCaptions":
        return SceneCaptions(self, [c for c in self.chunks if c["words"][0]["scene"] == scene])

    def _draw(self, words: list[dict], active: int) -> Image.Image:
        toks = [w["word"].upper() if self.upper else w["word"] for w in words]
        f = self.font
        tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        lines = _wrap(tmp, toks, f, 960)
        asc, desc = f.getmetrics()
        lh = asc + desc
        sw = 8
        space = tmp.textlength(" ", font=f)
        img = Image.new("RGBA", (W, lh * len(lines) + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for li, idxs in enumerate(lines):
            total = sum(tmp.textlength(toks[i], font=f) for i in idxs) + space * (len(idxs) - 1)
            x, y = (W - total) / 2, 20 + li * lh
            for i in idxs:
                fill = self.accent if i == active else (255, 255, 255)
                d.text((x, y), toks[i], font=f, fill=fill, stroke_width=sw, stroke_fill=(0, 0, 0))
                x += tmp.textlength(toks[i], font=f) + space
        return img


class SceneCaptions:
    def __init__(self, parent: Captions, chunks: list[dict]):
        self.parent, self.chunks, self.i, self.cache = parent, chunks, 0, {}

    def image(self, t: float) -> Image.Image | None:
        while self.i < len(self.chunks) and t >= self.chunks[self.i]["end"]:
            self.i += 1
        if self.i >= len(self.chunks) or t < self.chunks[self.i]["start"]:
            return None
        ch = self.chunks[self.i]
        active = max(k for k, w in enumerate(ch["words"]) if w["start"] <= t or k == 0)
        key = (self.i, active)
        if key not in self.cache:
            self.cache = {key: self.parent._draw(ch["words"], active)}
        return self.cache[key]


def _same(a: str, b: str) -> bool:
    n = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    return bool(a) and n(a) == n(b)


def paste_center(frame: Image.Image, img: Image.Image, cy: float, fade: float = 1.0) -> None:
    mask = img.split()[3]
    if fade < 1:
        mask = mask.point(lambda v: int(v * fade))
    frame.paste(img, (round((W - img.width) / 2), round(cy - img.height / 2)), mask)


# ---- sound ------------------------------------------------------------------------------

def paper_sfx() -> Path:
    """Synthesised page-turn swish (no download needed)."""
    out = config.DATA / "page_turn.wav"
    if out.exists():
        return out
    sr, n = 44100, int(0.42 * 44100)
    noise = np.random.default_rng(7).standard_normal(n)
    band = np.convolve(noise, np.ones(5) / 5, "same") - np.convolve(noise, np.ones(70) / 70, "same")
    t = np.linspace(0, 1, n)
    env = np.clip(t / 0.15, 0, 1) * np.exp(-np.clip(t - 0.15, 0, None) * 5)
    env *= 0.7 + 0.3 * np.sin(2 * np.pi * 19 * t) ** 2
    sig = band * env
    sig = (sig / np.abs(sig).max() * 0.55 * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(sig.tobytes())
    return out


def mix_audio(video: Path, voices: list, sfx: list, music: Path | None, music_volume: float, total: float,
              out: Path) -> None:
    args, fl = ["-i", video], []
    idx = 1

    def add(items, prefix, vol):
        nonlocal idx
        labels = []
        for p, start in items:
            args.extend(["-i", p])
            ms = max(0, int(start * 1000))
            fl.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,volume={vol},"
                      f"adelay={ms}:all=1[{prefix}{idx}]")
            labels.append(f"[{prefix}{idx}]")
            idx += 1
        return labels

    v_labels = add(voices, "v", 1.0)
    s_labels = add(sfx, "s", 0.5)
    final = []
    if v_labels:
        fl.append("".join(v_labels) + (f"amix=inputs={len(v_labels)}:normalize=0" if len(v_labels) > 1 else "anull")
                  + "[vo]")
    if s_labels:
        fl.append("".join(s_labels) + (f"amix=inputs={len(s_labels)}:normalize=0" if len(s_labels) > 1 else "anull")
                  + "[fx]")
        final.append("[fx]")
    if music:
        args.extend(["-stream_loop", "-1", "-i", music])
        fl.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{total:.2f},"
                  f"volume={music_volume},afade=t=in:d=0.5,afade=t=out:st={max(0, total - 1.8):.2f}:d=1.8[mu]")
        if v_labels:  # music dips under the narrator
            fl.append("[vo]asplit=2[vmain][vkey]")
            fl.append("[mu][vkey]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=350[mud]")
            final += ["[mud]", "[vmain]"]
        else:
            final.append("[mu]")
    elif v_labels:
        final.append("[vo]")
    if not final:
        args.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"])
        fl.append(f"[{idx}:a]anull[out0]")
        final = ["[out0]"]
    fl.append("".join(final) + (f"amix=inputs={len(final)}:normalize=0," if len(final) > 1 else "")
              + f"apad,atrim=0:{total:.2f},alimiter=limit=0.95[aout]")
    ff.run([*args, "-filter_complex", ";".join(fl), "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", "-movflags", "+faststart", out])


# ---- planning --------------------------------------------------------------------------

def voiced(s: dict) -> bool:
    return bool((s.get("voiceover") or "").strip())


def plan_timeline(scenes: list[dict], voice_name: str, instructions: str, assets: Path, progress) -> tuple:
    """Record narration (one take per run of voiced scenes, so it flows naturally), then time each scene to it."""
    t, clips, words_all = 0.0, [], []
    i = 0
    while i < len(scenes):
        if not voiced(scenes[i]):
            d = min(max(float(scenes[i].get("seconds") or SILENT_DEFAULT), 1.5), 8.0)
            scenes[i]["start"], scenes[i]["dur"] = t, d
            t += d
            i += 1
            continue
        j = i
        while j < len(scenes) and voiced(scenes[j]):
            j += 1
        run = scenes[i:j]
        text = " ".join(s["voiceover"].strip() for s in run)
        progress("Recording the voiceover...")
        wav = voice.speak(text, voice_name, instructions, assets)
        adur = ff.duration(wav)
        progress("Syncing captions to the voice (runs on your PC)...")
        words = align_words(text, wav)
        base = t + LEAD
        clips.append((wav, base))
        idx, starts = 0, []
        for k, s in enumerate(run):
            n = len(s["voiceover"].split())
            starts.append(words[idx]["start"] if idx < len(words) else adur)
            for w in words[idx:idx + n]:
                words_all.append({"word": w["word"], "start": base + w["start"], "end": base + w["end"],
                                  "scene": i + k})
            idx += n
        bounds = [t] + [base + st - 0.08 for st in starts[1:]] + [base + adur + TAIL]
        for k in range(1, len(bounds)):
            bounds[k] = max(bounds[k], bounds[k - 1] + 0.6)
        for k, s in enumerate(run):
            s["start"], s["dur"] = bounds[k], bounds[k + 1] - bounds[k]
        t = bounds[-1]
        i = j
    if scenes and scenes[-1]["dur"] < LAST_SCENE_MIN:
        t += LAST_SCENE_MIN - scenes[-1]["dur"]
        scenes[-1]["dur"] = LAST_SCENE_MIN
    return t, clips, words_all


def estimate(book: dict, variant: dict) -> dict:
    """Upper-bound cost of rendering (already-made images/clips are reused for free)."""
    g = GENRES[book["genre"]]
    scenes = variant.get("scenes", [])
    chars = sum(len(s.get("voiceover") or "") for s in scenes) + len(g["voice_instructions"]) * 2
    n_img = sum(1 for s in scenes if s.get("visual") in ("character", "ai_image"))
    n_img += sum(1 for s in scenes if s.get("visual") == "stock" and not config.PEXELS_API_KEY)
    n_img += sum(1 for s in scenes if s.get("visual") == "ai_video" and s.get("character"))
    n_img += 0 if book.get("background") else 1  # one-time desk photo
    vid_secs = sum(min(10, max(2, round(float(s.get("seconds") or 4) + 1)))
                   for s in scenes if s.get("visual") == "ai_video")
    out = {
        "voice": budget.tts_cost(config.TTS_MODEL, chars),
        "images": n_img * budget.image_cost(config.IMAGE_MODEL, config.IMAGE_QUALITY),
        "ai_video": budget.video_cost(config.VIDEO_MODEL, vid_secs) if vid_secs else 0.0,
    }
    out["total"] = round(sum(out.values()), 3)
    return out


def _broll_clips(book: dict) -> list[Path]:
    d = bk.book_dir(book["id"]) / "broll"
    return sorted(p for p in d.glob("*") if p.suffix.lower() in (".mp4", ".mov", ".m4v", ".webm")) if d.exists() else []


def build_source(book: dict, s: dict, idx: int, desk: Image.Image, assets: Path, warn, progress):
    vis, dur = s.get("visual", "cover"), s["dur"]
    seed = seed_for(book["id"], idx, s.get("prompt", ""), s.get("page", ""))
    try:
        if vis in ("page", "flip"):
            flips = int(s.get("flips") if s.get("flips") not in (None, "") else (4 if vis == "flip" else 1))
            return PageScene(book, desk, int(s.get("page") or 1), s.get("highlight") or "", dur, flips, seed)
        if vis == "cover":
            return CoverScene(book, desk, dur, seed)
        if vis == "broll":
            clips = _broll_clips(book)
            if clips:
                pick = next((c for c in clips if c.name == s.get("broll")), clips[idx % len(clips)])
                return VideoScene(pick, dur)
            warn(f"Scene {idx + 1}: no B-roll uploaded, using an AI photo instead.")
            vis = "ai_image"
        if vis == "stock":
            clip = visuals.stock_video(s.get("stock_query") or s.get("prompt") or "reading book", assets,
                                       min_seconds=min(dur, 5))
            if clip:
                return VideoScene(clip, dur)
            warn(f"Scene {idx + 1}: no stock clip found (add a free PEXELS_API_KEY), using an AI photo instead.")
            vis = "ai_image"
        prompt = s.get("prompt") or s.get("stock_query") or s.get("overlay") or book["title"]
        refs: list[Path] = []
        if s.get("character"):
            prompt, refs = visuals.character_prompt(book, s["character"], prompt)
        if vis == "ai_video":
            start = visuals.ai_image(prompt, assets, refs) if refs else None  # same face, now moving
            progress(f"Scene {idx + 1}: generating AI video (takes 1-3 min)...")
            return VideoScene(visuals.ai_video(prompt, dur, assets, start, progress), dur)
        progress(f"Scene {idx + 1}: generating AI photo...")
        return StillScene(visuals.ai_image(prompt, assets, refs), dur, seed)
    except Exception as e:  # never lose the whole video to one scene
        warn(f"Scene {idx + 1} ({vis}) failed: {str(e)[:200]} - showing the book instead.")
        quotes = (book.get("digest") or {}).get("quotes") or book.get("featured") or []
        if vis not in ("page", "flip") and quotes and bk.path(book, "manuscript"):
            q = quotes[idx % len(quotes)]
            try:
                return PageScene(book, desk, int(q.get("page") or 1), q.get("text", ""), dur, 1, seed)
            except Exception:
                pass
        return CoverScene(book, desk, dur, seed)


# ---- main --------------------------------------------------------------------------------

def _segment(s: dict, idx: int, f0: int, f1: int, cap, out: Path, tick) -> None:
    """Draw frames f0..f1 (global frame numbers) of one scene, with its text, straight into an H.264 file."""
    with tempfile.TemporaryFile() as errlog:
        enc = subprocess.Popen(
            [ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "faster", "-crf", "19",
             "-pix_fmt", "yuv420p", "-threads", "2", str(out)],
            stdin=subprocess.PIPE, stderr=errlog)
        try:
            for f in range(f0, max(f1, f0 + 1)):
                lt = (f - f0) / FPS
                frame = s["src"].frame(lt)
                if s.get("ov_img") is not None:
                    paste_center(frame, s["ov_img"], s["ov_y"], min(1.0, (lt + 0.02) / 0.15))
                if s.get("footer") is not None:
                    paste_center(frame, s["footer"], H * 0.9)
                if cap:
                    ci = cap.image(f / FPS)
                    if ci is not None:
                        paste_center(frame, ci, s["cap_y"])
                enc.stdin.write(frame.tobytes())
                tick()
        finally:
            if hasattr(s["src"], "close"):
                s["src"].close()
            try:
                enc.stdin.close()
            except OSError:
                pass
            enc.wait()
        if enc.returncode != 0:
            errlog.seek(0)
            raise RuntimeError(f"Encoding scene {idx + 1} failed: " + errlog.read().decode(errors="replace")[-1500:])


def render(book: dict, variant: dict, voice_name: str | None = None, captions: bool = True,
           music: Path | None = None, music_volume: float = 0.25, page_sound: bool = True,
           progress=lambda msg, frac=None: None) -> Path:
    g = GENRES[book["genre"]]
    scenes = [dict(s) for s in variant.get("scenes", []) if s]
    if not scenes:
        raise ValueError("This script has no scenes.")
    est = estimate(book, variant)
    budget.guard(est["total"] * 0.5, "render (voice + images + video)")  # each call is guarded again as it happens
    spent_before = budget.spent_this_month()

    assets = bk.book_dir(book["id"]) / "assets"
    assets.mkdir(exist_ok=True)
    out_dir = config.PROJECTS_DIR / book["id"] / f"{datetime.now():%Y%m%d-%H%M%S}-{bk.slug(variant.get('name', 'video'))[:28]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    def warn(msg):
        warnings.append(msg)
        progress(msg)

    total, clips, words = plan_timeline(scenes, voice_name or g["voice"], g["voice_instructions"], assets, progress)

    progress("Setting up the desk...")
    if not book.get("background") and (config.OPENAI_API_KEY or config.XAI_API_KEY):
        try:  # one realistic desk photo per book (~$0.015), reused for every video
            visuals.make_background(book)
        except Exception as e:
            warn(f"Could not create the AI desk photo ({str(e)[:120]}); using a plain wood background.")
    desk = desk_canvas(book)
    for i, s in enumerate(scenes):
        progress(f"Preparing scene {i + 1}/{len(scenes)} ({s.get('visual')})...", 0.05 + 0.25 * i / len(scenes))
        s["src"] = build_source(book, s, i, desk, assets, warn, progress)

    # text layers
    accent = ass_to_rgb(g["accent"])
    poetic = book["genre"] == "poetry"
    for i, s in enumerate(scenes):
        ov = (s.get("overlay") or "").strip()
        if book["genre"] == "medical" and i == len(scenes) - 1 and "not medical advice" not in ov.lower():
            s["footer"] = text_card("Educational only - not medical advice.", "Arial", 30, "shadow", 900)
        if ov and not (captions and _same(ov, s.get("voiceover", ""))):
            hook = i == 0 and not poetic
            s["ov_img"] = text_card(ov, "Arial Black" if hook else g["font"], 60 if hook else 56,
                                    "box" if hook else "shadow")
        desky = s.get("visual") in ("page", "flip", "cover")
        s["ov_y"] = H * (0.13 if desky else 0.22)
        s["cap_y"] = H * (0.77 if desky else 0.64)
    cap = Captions(words, g["caption_font"], accent, g["caption_font"] == "Arial Black") if captions and words else None

    sfx = []
    if page_sound:
        for s in scenes:
            for ft in getattr(s["src"], "flip_times", []):
                sfx.append((paper_sfx(), s["start"] + ft))

    # draw + encode every scene as its own segment, two at a time (Pillow releases the GIL while it works)
    bounds = [int(round(sc["start"] * FPS)) for sc in scenes] + [int(round(total * FPS))]
    n_frames = bounds[-1]
    done = [0]
    lock = threading.Lock()

    def tick():
        with lock:
            done[0] += 1
            if done[0] % 15 == 0:
                progress(f"Drawing frames {done[0]}/{n_frames}", 0.3 + 0.62 * done[0] / n_frames)

    segs = [out_dir / f"seg_{i:02d}.mp4" for i in range(len(scenes))]
    workers = max(1, min(3, (os.cpu_count() or 2) // 2))
    with ThreadPoolExecutor(workers) as pool:
        jobs = [pool.submit(_segment, sc, i, bounds[i], bounds[i + 1], cap.for_scene(i) if cap else None, segs[i], tick)
                for i, sc in enumerate(scenes)]
        for j in jobs:
            j.result()
    silent = out_dir / "video_only.mp4"
    lst = out_dir / "segments.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in segs), encoding="utf-8")
    ff.run(["-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", silent.name], cwd=out_dir)
    for p in [*segs, lst]:
        p.unlink(missing_ok=True)

    progress("Mixing voice, music and sound...", 0.95)
    final = out_dir / "final.mp4"
    mix_audio(silent, clips, sfx, music, music_volume, total, final)
    silent.unlink(missing_ok=True)

    meta = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "book": book["id"], "variant": {k: v for k, v in variant.items()},
        "timeline": [{k: s[k] for k in ("beat", "visual", "start", "dur") if k in s} for s in scenes],
        "seconds": round(total, 2), "voice": voice_name or g["voice"], "captions": captions,
        "music": music.name if music else None, "cost": round(budget.spent_this_month() - spent_before, 4),
        "warnings": warnings, "file": final.name,
    }
    (out_dir / "render.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    progress("Done!", 1.0)
    return final


def list_renders(book_id: str) -> list[dict]:
    out = []
    for p in sorted((config.PROJECTS_DIR / book_id).glob("*/render.json"), reverse=True):
        m = json.loads(p.read_text(encoding="utf-8"))
        m["dir"] = str(p.parent)
        m["path"] = str(p.parent / m.get("file", "final.mp4"))
        out.append(m)
    return out


def update_render(render_dir: str, **fields) -> None:
    p = Path(render_dir) / "render.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    m.update(fields)
    p.write_text(json.dumps(m, indent=1), encoding="utf-8")

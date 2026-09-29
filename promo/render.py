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
import time
import wave
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import book as bk, budget, config, ffmpeg_utils as ff, qa, sfx, visuals, voice
from .genres import GENRES
from .transcribe import align_words

W, H, FPS = config.W, config.H, config.FPS
S = 1.5                      # desk scenes are composed larger than the output so the camera can push in sharply
CW, CH = int(W * S), int(H * S)
K = 1.0                      # text/size scale relative to 1080p (0.667 for a 720p draft)
PRESET, CRF = "faster", "19"


def use_size(draft: bool) -> None:
    """Draft = 720x1280 with a quicker encode (~2x faster, fine for checking); final = 1080x1920."""
    global W, H, CW, CH, K, PRESET, CRF
    W, H = (720, 1280) if draft else (config.W, config.H)
    CW, CH = int(W * S), int(H * S)
    K = W / 1080
    PRESET, CRF = ("veryfast", "23") if draft else ("faster", "19")
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
        self.S = 1.8                          # sharper canvas: the camera pushes in further on the text
        self.CW, self.CH = int(W * self.S), int(H * self.S)
        n_pages = max(1, bk.page_count(book))
        page_no = max(1, min(page_no, n_pages))
        tgt, boxes = bk.render_page(book, page_no, highlight)
        spread = page_no > 1                  # there is a left-hand page -> frame it as an open book
        pw = int(self.CW * (0.66 if spread else 0.8))
        sc = pw / tgt.width
        if tgt.height * sc > self.CH * 0.86:
            sc = self.CH * 0.86 / tgt.height
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
        self.cc = (self.CW * (0.6 if spread else 0.5), self.CH * 0.5)
        self.pc = (pw / 2, ph / 2)
        self.desk = desk.resize((self.CW, self.CH), Image.BILINEAR)
        darken(self.desk, soft_shadow((pw, ph), self.angle), (self.cc[0] + 16 * self.S, self.cc[1] + 24 * self.S))
        self.gutter = self._gutter()
        self._edges = self._stack_edges()

        n = len(self.prev)
        self.hold = 0.3 if n else 0.0
        self.turn = (0.85 if n == 1 else 0.42) if n else 0.0
        if n and self.hold + n * self.turn > dur * 0.55:
            self.turn = max(0.24, (dur * 0.55 - self.hold) / n)
        self.flip_end = self.hold + n * self.turn
        self.flip_events = [(self.hold + i * self.turn, self.turn) for i in range(n)]  # (start, length) for sound
        self.hl_start = self.flip_end + 0.15
        self.hl_dur = min(1.2, max(0.5, 0.1 * len(self.boxes)))
        fx, fy = bk.highlight_focus(self.target, self.boxes) if self.boxes else (0.5, 0.36)
        self.focus = rot(fx * pw, fy * ph, self.angle, self.pc, self.cc)
        self.zoom_end = 1.35
        if self.boxes:  # push in close, but keep the whole highlighted passage in frame
            xs = [x for b in self.boxes for x in (b[0], b[2])]
            ys = [y for b in self.boxes for y in (b[1], b[3])]
            self.zoom_end = max(1.2, min(self.CW / (pw * 1.08), self.CH * 0.45 / max(1, max(ys) - min(ys))))
            # keep whole lines in view: centre on the page column, at the height of the quote
            self.focus = (rot(pw / 2, 0, self.angle, self.pc, self.cc)[0], self.focus[1])
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

    def _stack_edges(self) -> list[Image.Image]:
        """Pre-rotated paper layers peeking out under the top page = the book block's edges."""
        out = []
        for k, tone in ((4, (196, 188, 170)), (3, (212, 204, 187)), (2, (224, 217, 200)), (1, (234, 228, 212))):
            layer = Image.new("RGBA", (self.pw, self.ph), tone + (255,))
            out.append((k, layer.rotate(self.angle, resample=Image.BICUBIC, expand=True)))
        return out

    def _place_edges(self, c: Image.Image, side: int) -> None:
        for k, layer in self._edges:
            ox = side * k * 1.5 * self.S
            cx, cy = rot(self.pw / 2 + ox, self.ph / 2 + k * 1.1 * self.S, self.angle, self.pc, self.cc) if side > 0 else \
                rot(-self.pw / 2 + ox, self.ph / 2 + k * 1.1 * self.S, self.angle, self.pc, self.cc)
            c.paste(layer, (round(cx - layer.width / 2), round(cy - layer.height / 2)), layer)

    def _canvas(self, top: Image.Image, left: Image.Image | None, hl: float = 0.0) -> Image.Image:
        key = (id(top), id(left), hl)
        if key in self._cache:
            return self._cache[key]
        if 0 < hl < 1:
            c = self._partial(self._canvas(top, left, 0.0), self._canvas(top, left, 1.0), hl)
        else:
            c = self.desk.copy()
            if left is not None:
                self._place_edges(c, -1)
                place(c, left, self.angle, rot(-self.pw / 2, self.ph / 2, self.angle, self.pc, self.cc))
            self._place_edges(c, 1)
            place(c, bk.apply_highlight(top, self.boxes, 1.0) if hl >= 1 else top, self.angle, self.cc)
            if left is not None:
                darken(c, self.gutter, rot(0, self.ph / 2, self.angle, self.pc, self.cc))
        if len(self._cache) > 2:  # each canvas is ~20 MB: keep only the clean + fully highlighted page
            self._cache = {k: v for k, v in self._cache.items() if k[2] in (0.0, 1.0)}
            while len(self._cache) > 2:
                self._cache.pop(next(iter(self._cache)))
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

    SEG = 28                                   # strips the bending sheet is drawn with
    LIGHT = (-0.45, 0.893)                     # light from the upper left (x, z), normalised
    HALF = (-0.231, 0.973)                     # half-vector between light and camera, for the sheen

    def _sheet(self, u: float) -> list[tuple]:
        """Cross-section of the turning sheet from spine to free edge: [(s, x, z, phi_of_segment)].
        The sheet bends: its free edge leads while it lifts and trails while it lands, like a real page."""
        th = math.pi * u
        bend = 0.75 * math.sin(2 * math.pi * u) + 0.35 * math.sin(math.pi * u)
        pts, x, z, ds = [(0.0, 0.0, 0.0, th)], 0.0, 0.0, 1.0 / self.SEG
        for k in range(self.SEG):
            phi = min(math.pi, max(0.0, th + bend * ((k + 0.5) * ds) ** 1.6))
            x += math.cos(phi) * ds * self.pw
            z += math.sin(phi) * ds * self.pw
            pts.append(((k + 1) * ds, x, z, phi))
        return pts

    def _proj(self, x: float, z: float, y: float) -> tuple[float, float]:
        """Perspective from a camera above the desk: higher parts of the sheet look bigger."""
        f = 1.9 * self.ph / (1.9 * self.ph - z)
        return self.pw / 2 + (x - self.pw / 2) * f, self.ph / 2 + (y - self.ph / 2) * f

    def _turning(self, c: Image.Image, i: int, u: float) -> None:
        """Draw sheet i curling over the spine (u 0 -> 1), with its cast shadow and curved shading."""
        if u <= 0.001 or u >= 0.999:
            return
        pw, ph = self.pw, self.ph
        pts = self._sheet(u)
        to_canvas = lambda x, y: rot(x, y, self.angle, self.pc, self.cc)

        # shadow on the page below: each point drops toward the lower right by its height; softer when higher
        zmax = max(p[2] for p in pts)
        if zmax > 2:
            poly = [to_canvas(x + z * 0.5, 0 + z * 0.22) for _, x, z, _ in pts]
            poly += [to_canvas(x + z * 0.5, ph + z * 0.22) for _, x, z, _ in reversed(pts)]
            q = 4
            mx0, my0 = min(p[0] for p in poly) - 80, min(p[1] for p in poly) - 80
            mw, mh = int(max(p[0] for p in poly) - mx0 + 80), int(max(p[1] for p in poly) - my0 + 80)
            m = Image.new("L", (mw // q + 1, mh // q + 1), 0)
            strength = int(135 * (1 - math.exp(-zmax / (0.12 * pw))) * (0.55 + 0.45 * math.sin(math.pi * u)))
            ImageDraw.Draw(m).polygon([((x - mx0) / q, (y - my0) / q) for x, y in poly], fill=strength)
            m = m.filter(ImageFilter.GaussianBlur((6 + 0.05 * zmax / self.S) * self.S / q)).resize((mw, mh), Image.BILINEAR)
            c.paste((0, 0, 0), (int(mx0), int(my0), int(mx0) + mw, int(my0) + mh), m)

        # the sheet itself, strip by strip, lowest first so higher parts cover lower ones
        W, H = self.prev_rgba[i].size
        segs = sorted(range(self.SEG), key=lambda k: pts[k][2] + pts[k + 1][2])
        for k in segs:
            s0, x0, z0, _ = pts[k]
            s1, x1, z1, phi = pts[k + 1]
            front = math.cos(phi) >= 0
            X0, T0 = self._proj(x0, z0, 0)
            X1, T1 = self._proj(x1, z1, 0)
            _, B0 = self._proj(x0, z0, ph)
            _, B1 = self._proj(x1, z1, ph)
            if abs(X1 - X0) < 0.4:
                continue
            d = math.copysign(0.8, X1 - X0)       # overlap strips a hair so no seams show
            quad = [to_canvas(X0 - d, T0), to_canvas(X1 + d, T1), to_canvas(X1 + d, B1), to_canvas(X0 - d, B0)]
            if front:
                img, c0, c1 = self.prev_rgba[i], s0 * W, s1 * W
                nx, nz = -math.sin(phi), math.cos(phi)
            else:
                img, c0, c1 = self.backs_rgba[i], (1 - s0) * W, (1 - s1) * W
                nx, nz = math.sin(phi), -math.cos(phi)
            lam = max(0.0, nx * self.LIGHT[0] + nz * self.LIGHT[1]) / self.LIGHT[1]
            bright = min(1.02, 0.58 + 0.42 * lam)
            sheen = 0.07 * max(0.0, nx * self.HALF[0] + nz * self.HALF[1]) ** 90
            xs, ys = [p[0] for p in quad], [p[1] for p in quad]
            bx, by = math.floor(min(xs)), math.floor(min(ys))
            bw, bh = math.ceil(max(xs)) - bx, math.ceil(max(ys)) - by
            if bw < 1 or bh < 2:
                continue
            piece = img.transform((bw, bh), Image.PERSPECTIVE,
                                  persp_coeffs([(x - bx, y - by) for x, y in quad],
                                               [(c0, 0), (c1, 0), (c1, H), (c0, H)]), Image.BILINEAR)
            lut = [min(255, int(v * bright + sheen * 255)) for v in range(256)]
            piece = piece.point(lut * 3 + list(range(256)))   # shade colour, keep transparency
            c.paste(piece, (bx, by), piece)

        # the free edge catches a thin dark line (paper thickness)
        _, xe, ze, phe = pts[-1]
        xa, ta = self._proj(xe, ze, 0)
        _, ba = self._proj(xe, ze, ph)
        edge = (178, 168, 150) if math.cos(phe) >= 0 else (160, 151, 134)
        ImageDraw.Draw(c).line([to_canvas(xa, ta), to_canvas(xa, ba)], fill=edge, width=max(1, int(1.4 * self.S)))

    def frame(self, t: float) -> Image.Image:
        n = len(self.prev)
        if n and t < self.flip_end:
            i = 0 if t < self.hold else min(n - 1, int((t - self.hold) // self.turn))
            beneath = self.prev[i + 1] if i + 1 < n else self.target
            left = self.backs[i - 1] if i > 0 else self.initial_left
            base = self._canvas(beneath, left)

            def at(tt: float) -> float:
                x = (tt - self.hold - i * self.turn) / self.turn
                return 0.0 if tt < self.hold else 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, x)))

            c = base.copy()
            self._turning(c, i, at(t))
            return camera(c, 1.02, self.CW / 2, self.CH / 2, t)
        left = self.backs[-1] if n else self.initial_left
        hl = round(ease((t - self.hl_start) / self.hl_dur) * 16) / 16 if self.boxes else 0.0
        c = self._canvas(self.target, left, hl)
        u = ease((t - self.flip_end) / max(0.4, self.dur - self.flip_end - 0.1))
        zoom = 1.02 + (self.zoom_end - 1.02) * u
        cx = self.CW / 2 + (self.focus[0] - self.CW / 2) * u
        cy = self.CH / 2 + (self.focus[1] - self.CH / 2) * u
        return camera(c, zoom, cx, cy, t)


class CoverScene:
    """The physical book is set down on the desk: it lowers into place in slight perspective, its shadow tightens
    as it touches the table, light glints across the cover, the camera eases in."""

    F = 0.955      # far (top) edge looks a little narrower: the camera is slightly in front of the book
    V = 0.97       # slight foreshortening of the book's length
    LIGHT = (0.55, 0.45)  # shadows fall toward the lower right (light from the upper left)

    def __init__(self, book: dict, desk: Image.Image, dur: float, seed: int):
        rnd = random.Random(seed)
        self.dur, self.desk = dur, desk
        self.angle = math.radians(rnd.uniform(-3.5, -1.2))
        cover = bk.cover_image(book)
        w = int(CW * 0.5)
        h = int(cover.height * w / cover.width)
        if h > CH * 0.56:
            h = int(CH * 0.56)
            w = int(cover.width * h / cover.height)
        self.w, self.h = w, h
        self.t = max(6, int(h * 0.028))           # thickness of the page block
        self.cover = self._lit(cover.resize((w, h), Image.LANCZOS))
        self.pages = self._page_edge(w, self.t * 3)
        self.center = (CW / 2, CH * 0.52)
        self.land = min(0.75, dur * 0.3)
        self.static = None
        self.static_quad = None

    # ---- look ----
    def _lit(self, cover: Image.Image) -> Image.Image:
        """Match the cover to the photo: light falling from the upper left, a touch of the desk's colour,
        a darker hinge by the spine, soft edges and photo grain - so it doesn't look pasted on."""
        w, h = cover.size
        from PIL import ImageChops
        yy, xx = np.mgrid[0:h, 0:w]
        diag = (xx / max(1, w - 1) + yy / max(1, h - 1)) / 2                          # 0 top-left .. 1 bottom-right
        light = Image.fromarray((255 * (1.04 - 0.18 * diag) / 1.1).clip(0, 255).astype(np.uint8), "L")
        lit = ImageChops.multiply(cover, Image.merge("RGB", [light] * 3))
        lit = Image.eval(lit, lambda v: min(255, int(v * 1.1)))                        # undo the multiply's dimming
        sample = self.desk.resize((16, 28), Image.BILINEAR).crop((3, 6, 13, 22))
        tint = sample.resize((1, 1), Image.BILINEAR).getpixel((0, 0))
        m = max(1, max(tint))
        cast = Image.new("RGB", (w, h), tuple(int(200 + 55 * c / m) for c in tint))      # warm/cool cast of the room
        lit = Image.blend(lit, ImageChops.multiply(lit, cast), 0.35)
        hinge = Image.new("L", (w, h), 0)
        hd = ImageDraw.Draw(hinge)
        for x in range(int(w * 0.06)):
            hd.line([(x, 0), (x, h)], fill=int(90 * (1 - x / (w * 0.06)) ** 1.5))
        edge = Image.new("L", (w, h), 0)
        ImageDraw.Draw(edge).rectangle((0, 0, w - 1, h - 1), outline=60, width=max(2, w // 220))
        lit.paste((0, 0, 0), (0, 0), ImageChops.lighter(hinge, edge.filter(ImageFilter.GaussianBlur(2))))
        grain = Image.effect_noise((w, h), 22).convert("RGB")
        lit = Image.blend(lit, grain, 0.035).filter(ImageFilter.GaussianBlur(0.5))
        return lit.convert("RGBA")

    @staticmethod
    def _page_edge(w: int, h: int) -> Image.Image:
        """Cream page block with fine page lines, darker toward the table."""
        img = Image.new("RGB", (w, h), (232, 224, 205))
        d = ImageDraw.Draw(img)
        rnd = random.Random(w)
        for y in range(h):
            shade = int(232 - 38 * y / h) - rnd.randint(0, 9)
            d.line([(0, y), (w, y)], fill=(shade, shade - 7, shade - 20))
        return img.convert("RGBA")

    # ---- geometry ----
    def _quad(self, scale: float, lift: float) -> list[tuple]:
        """Top face of the book: far edge narrower (perspective), rotated a little, lifted toward the camera."""
        hw, hh = self.w / 2 * scale, self.h / 2 * scale * self.V
        pts = [(-hw * self.F, -hh), (hw * self.F, -hh), (hw, hh), (-hw, hh)]
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        cx, cy = self.center[0], self.center[1] - lift
        return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]

    def _map(self, c: Image.Image, img: Image.Image, quad: list[tuple]) -> None:
        xs, ys = [p[0] for p in quad], [p[1] for p in quad]
        x0, y0 = math.floor(min(xs)), math.floor(min(ys))
        bw, bh = math.ceil(max(xs)) - x0, math.ceil(max(ys)) - y0
        W_, H_ = img.size
        piece = img.transform((bw, bh), Image.PERSPECTIVE,
                              persp_coeffs([(x - x0, y - y0) for x, y in quad], [(0, 0), (W_, 0), (W_, H_), (0, H_)]),
                              Image.BICUBIC)
        c.paste(piece, (x0, y0), piece)

    def _shadow(self, c: Image.Image, poly: list[tuple], blur: float, alpha: int) -> None:
        q = 4
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        pad = blur * 3 + 10
        x0, y0 = int(min(xs) - pad), int(min(ys) - pad)
        mw, mh = int(max(xs) + pad) - x0, int(max(ys) + pad) - y0
        m = Image.new("L", (mw // q + 1, mh // q + 1), 0)
        ImageDraw.Draw(m).polygon([((x - x0) / q, (y - y0) / q) for x, y in poly], fill=alpha)
        m = m.filter(ImageFilter.GaussianBlur(max(0.5, blur / q))).resize((mw, mh), Image.BILINEAR)
        c.paste((0, 0, 0), (x0, y0, x0 + mw, y0 + mh), m)

    def _compose(self, z: float) -> tuple[Image.Image, list]:
        """z = height above the desk, 0 (resting) .. 1 (just picked up)."""
        c = self.desk.copy()
        rest = self._quad(1.0, 0)
        t = self.t
        footprint = rest[:2] + [(rest[2][0], rest[2][1] + t), (rest[3][0], rest[3][1] + t)]
        lx, ly = self.LIGHT
        # soft shadow cast away from the light; further and softer the higher the book is
        off = (self.w * (0.03 + 0.1 * z) * lx / 0.55, self.h * (0.025 + 0.08 * z) * ly / 0.45)
        self._shadow(c, [(x + off[0], y + off[1]) for x, y in footprint], blur=(14 + 50 * z) * S,
                     alpha=int(150 * (1 - 0.45 * z)))
        # tight contact shadow where the book touches the table (fades in as it lands)
        if z < 0.35:
            k = 1 - z / 0.35
            self._shadow(c, [(x + 1.5 * S, y + 2.5 * S) for x, y in footprint], blur=4 * S, alpha=int(210 * k))
        quad = self._quad(1 + 0.1 * z, lift=CH * 0.02 * z)
        tl, tr, br, bl = quad
        tz = t * (1 + 0.1 * z)
        self._map(c, self.pages, [bl, br, (br[0], br[1] + tz), (bl[0], bl[1] + tz)])     # page block (near edge)
        self._map(c, self.cover, quad)                                                  # the cover
        return c, quad

    def _glint(self, c: Image.Image, quad: list, u: float) -> Image.Image:
        q = 4
        xs, ys = [p[0] for p in quad], [p[1] for p in quad]
        x0, y0 = int(min(xs)), int(min(ys))
        w, h = int(max(xs)) - x0, int(max(ys)) - y0
        from PIL import ImageChops
        shape = Image.new("L", (w // q + 1, h // q + 1), 0)
        ImageDraw.Draw(shape).polygon([((x - x0) / q, (y - y0) / q) for x, y in quad], fill=255)
        band = Image.new("L", shape.size, 0)
        bx = (-w * 0.6 + u * w * 2.2) / q
        ImageDraw.Draw(band).polygon([(bx, 0), (bx + w * 0.2 / q, 0), (bx - w * 0.3 / q, h / q),
                                      (bx - w * 0.5 / q, h / q)], fill=46)
        band = ImageChops.multiply(band.filter(ImageFilter.GaussianBlur(22 * S / q)), shape)
        band = band.resize((w, h), Image.BILINEAR)
        c = c.copy()
        c.paste((255, 250, 240), (x0, y0, x0 + w, y0 + h), band)
        return c

    def frame(self, t: float) -> Image.Image:
        u = ease_out(t / self.land) if self.land > 0 else 1.0
        if u < 1:
            c, _ = self._compose(1 - u)
        else:
            if self.static is None:
                self.static, self.static_quad = self._compose(0.0)
            c = self.static
            g0 = self.land + 0.35
            if g0 <= t <= g0 + 1.0:
                c = self._glint(c, self.static_quad, (t - g0) / 1.0)
        zoom = 1.02 + 0.1 * ease((t - self.land) / max(0.5, self.dur - self.land))
        return camera(c, zoom, self.center[0], self.center[1], t)


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
        self.font = bk.font(font_name, int((84 if font_name == "Georgia" else 78) * K))
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
        lines = _wrap(tmp, toks, f, 960 * K)
        asc, desc = f.getmetrics()
        lh = asc + desc
        sw = max(3, int(8 * K))
        space = tmp.textlength(" ", font=f)
        img = Image.new("RGBA", (W, lh * len(lines) + int(40 * K)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for li, idxs in enumerate(lines):
            total = sum(tmp.textlength(toks[i], font=f) for i in idxs) + space * (len(idxs) - 1)
            x, y = (W - total) / 2, int(20 * K) + li * lh
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
    s_labels = add(sfx, "s", 0.6)
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
    if music:
        idx += 1
    # a silent bed exactly as long as the video: the mix always lasts the full length and always ends
    args.extend(["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"])
    fl.append(f"[{idx}:a]anull[bed]")
    final.append("[bed]")
    fl.append("".join(final) + f"amix=inputs={len(final)}:normalize=0:duration=longest,"
              + f"atrim=0:{total:.3f},alimiter=limit=0.95[aout]")
    ff.run([*args, "-filter_complex", ";".join(fl), "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", "-movflags", "+faststart", out])


# ---- planning --------------------------------------------------------------------------

def voiced(s: dict) -> bool:
    return bool((s.get("voiceover") or "").strip())


def plan_timeline(scenes: list[dict], voice_name: str, instructions: str, assets: Path, progress,
                  genre: str = "fiction") -> tuple:
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
        wav = voice.speak(text, voice_name, instructions, assets, genre)
        adur = ff.duration(wav)
        progress("Syncing captions to the voice (runs on your PC)...")
        words = align_words(text, wav, voice.timings(wav))
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


def estimate(book: dict, variant: dict, quality_check: bool = True) -> dict:
    """Upper-bound cost of rendering (already-made images/clips are reused for free)."""
    g = GENRES[book["genre"]]
    scenes = variant.get("scenes", [])
    chars = sum(len(s.get("voiceover") or "") for s in scenes)
    chars += len(g["voice_instructions"]) * 2 if config.TTS_PROVIDER == "openai" else 0
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
    if quality_check:  # vision checks (~$0.005 each) + the final look-through; re-makes only happen if needed
        n_ai = sum(1 for s in scenes if s.get("visual") in AI_KINDS)
        n_ai += 0 if config.PEXELS_API_KEY else sum(1 for s in scenes if s.get("visual") == "stock")
        out["quality_check"] = 0.005 * n_ai + 0.01
    out["total"] = round(sum(out.values()), 3)
    return out


def _broll_clips(book: dict) -> list[Path]:
    d = bk.book_dir(book["id"]) / "broll"
    return sorted(p for p in d.glob("*") if p.suffix.lower() in (".mp4", ".mov", ".m4v", ".webm")) if d.exists() else []


AI_KINDS = ("ai_image", "character", "ai_video")


def build_source(book: dict, s: dict, idx: int, desk: Image.Image, assets: Path, warn, progress,
                 check: bool = False, image_tries: int = 2, video_tries: int = 1, reports: list | None = None):
    """Make the picture for one scene. With `check`, every AI shot is reviewed and re-made until it looks real."""
    vis, dur = s.get("visual", "cover"), s["dur"]
    seed = seed_for(book["id"], idx, s.get("prompt", ""), s.get("page", ""))
    label = f"Scene {idx + 1}"
    s["_asset"], s["_kind"] = None, vis
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
            warn(f"{label}: no B-roll uploaded, using an AI photo instead.")
            vis = "ai_image"
        if vis == "stock":
            clip = visuals.stock_video(s.get("stock_query") or s.get("prompt") or "reading book", assets,
                                       min_seconds=min(dur, 5), skip=s.get("_stock_skip", 0))
            if clip:
                s["_asset"], s["_kind"] = clip, "stock"
                return VideoScene(clip, dur)
            warn(f"{label}: no stock clip found (add a free PEXELS_API_KEY), using an AI photo instead.")
            vis = "ai_image"
        prompt = s.get("_fixed_prompt") or s.get("prompt") or s.get("stock_query") or s.get("overlay") or book["title"]
        refs: list[Path] = []
        if s.get("character") and not s.get("_fixed_prompt"):
            prompt, refs = visuals.character_prompt(book, s["character"], prompt)
        elif s.get("character"):
            refs = visuals.character_prompt(book, s["character"], "")[1]
        base = s.get("_take", 0)

        def shot(gen, kind, tries, what):
            if not check:
                return gen(prompt, 0)
            path, report = qa.best_of(gen, prompt, kind, refs, tries, f"{label} {what}".strip(), progress)
            if reports is not None:
                reports.append(report)
            return path

        if vis == "ai_video":
            start = None
            if refs:  # same face, now moving: make (and check) the first frame, then animate it
                start = shot(lambda p, t: visuals.ai_image(p, assets, refs, take=base + t), "image", image_tries,
                             "start frame")
            progress(f"{label}: generating AI video (takes 1-3 min)...")
            clip = shot(lambda p, t: visuals.ai_video(p, dur, assets, start, progress, take=base + t), "video",
                        video_tries, "")
            s["_asset"], s["_kind"], s["_prompt"] = clip, "ai_video", prompt
            return VideoScene(clip, dur)
        progress(f"{label}: generating AI photo...")
        img = shot(lambda p, t: visuals.ai_image(p, assets, refs, take=base + t), "image", image_tries, "")
        s["_asset"], s["_kind"], s["_prompt"] = img, "ai_image", prompt
        return StillScene(img, dur, seed)
    except Exception as e:  # never lose the whole video to one scene
        warn(f"{label} ({vis}) failed: {str(e)[:200]} - showing the book instead.")
        quotes = (book.get("digest") or {}).get("quotes") or book.get("featured") or []
        if vis not in ("page", "flip") and quotes and bk.path(book, "manuscript"):
            q = quotes[idx % len(quotes)]
            try:
                return PageScene(book, desk, int(q.get("page") or 1), q.get("text", ""), dur, 1, seed)
            except Exception:
                pass
        return CoverScene(book, desk, dur, seed)


def _scene_brief(s: dict) -> str:
    vis = s.get("_kind") or s.get("visual")
    brief = s.get("_prompt") or s.get("prompt") or s.get("stock_query") or s.get("highlight") or ""
    return (f"{vis}; overlay text: '{s.get('overlay', '')}'; narration: '{s.get('voiceover', '')}'; "
            f"shot: {brief[:220]}")


# ---- main --------------------------------------------------------------------------------

def _segment(s: dict, idx: int, f0: int, f1: int, cap, out: Path, tick) -> None:
    """Draw frames f0..f1 (global frame numbers) of one scene, with its text, straight into an H.264 file."""
    with tempfile.TemporaryFile() as errlog:
        enc = subprocess.Popen(
            [ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
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


def _look_through(book, scenes, segs, bounds, cap, desk, assets, warn, progress, make) -> dict:
    """Watch the drawn video (one frame per scene, as viewers see it). Re-make AI/stock scenes that still look
    wrong and re-draw only those scenes."""
    progress("Looking through the finished video for flaws...", 0.93)
    frames = []
    for i, seg in enumerate(segs):
        mid = (bounds[i + 1] - bounds[i]) / FPS * 0.55
        fp = seg.with_suffix(".jpg")
        try:
            ff.run(["-ss", f"{mid:.2f}", "-i", seg, "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "4", fp])
            frames.append((i, fp, _scene_brief(scenes[i])))
        except Exception:
            pass
    verdict = qa.review_final(frames)
    remade = []
    for i, v in sorted(verdict["scenes"].items()):
        if not (0 <= i < len(scenes)) or v["score"] >= qa.FINAL_PASS:
            continue
        s = scenes[i]
        kind = s.get("_kind")
        problems = "; ".join(v["problems"][:2]) or "looks off"
        if kind not in ("ai_image", "ai_video", "stock"):
            warn(f"Final check, scene {i + 1}: {problems} (not an AI shot - edit the script to change it).")
            continue
        progress(f"Scene {i + 1} scored {v['score']}/10 in the final check ({problems}) - re-making it...")
        if kind == "stock":
            s["_stock_skip"] = s.get("_stock_skip", 0) + 1
        else:
            s["_fixed_prompt"] = v.get("fixed_prompt") or s.get("_prompt")
            s["_take"] = s.get("_take", 0) + 10
        s["src"] = build_source(book, s, i, desk, assets, warn, progress, **{**make, "image_tries": 1})
        _segment(s, i, bounds[i], bounds[i + 1], cap.for_scene(i) if cap else None, segs[i], lambda: None)
        remade.append({"scene": i + 1, "score": v["score"], "problems": v["problems"]})
    for _, fp, _ in frames:
        fp.unlink(missing_ok=True)
    return {"summary": verdict.get("summary", ""),
            "scores": {str(i + 1): v["score"] for i, v in verdict["scenes"].items()}, "remade": remade}


def render(book: dict, variant: dict, voice_name: str | None = None, captions: bool = True,
           music: Path | None = None, music_volume: float = 0.25, page_sound: bool = True,
           quality_check: bool = True, video_retries: int = 1, draft: bool = False,
           progress=lambda msg, frac=None: None, redo_of: str | None = None) -> Path:
    g = GENRES[book["genre"]]
    use_size(draft)
    options = {"voice_name": voice_name, "captions": captions, "music": str(music) if music else None,
               "music_volume": music_volume, "page_sound": page_sound, "quality_check": quality_check,
               "video_retries": video_retries, "draft": draft}
    scenes = [dict(s) for s in variant.get("scenes", []) if s]
    if not scenes:
        raise ValueError("This script has no scenes.")
    est = estimate(book, variant, quality_check)
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

    voice_name = voice_name or voice.default_voice(book["genre"])
    total, clips, words = plan_timeline(scenes, voice_name, g["voice_instructions"], assets, progress, book["genre"])

    progress("Setting up the desk...")
    if not book.get("background") and (config.OPENAI_API_KEY or config.XAI_API_KEY):
        try:  # one realistic desk photo per book (~$0.015), reused for every video
            visuals.make_background(book)
        except Exception as e:
            warn(f"Could not create the AI desk photo ({str(e)[:120]}); using a plain wood background.")
    desk = desk_canvas(book)
    qa_reports: list[dict] = []
    make = dict(check=quality_check, video_tries=video_retries, reports=qa_reports)
    for i, s in enumerate(scenes):
        progress(f"Preparing scene {i + 1}/{len(scenes)} ({s.get('visual')})...", 0.05 + 0.25 * i / len(scenes))
        s["src"] = build_source(book, s, i, desk, assets, warn, progress, **make)

    # text layers
    accent = ass_to_rgb(g["accent"])
    poetic = book["genre"] == "poetry"
    for i, s in enumerate(scenes):
        ov = (s.get("overlay") or "").strip()
        if book["genre"] == "medical" and i == len(scenes) - 1 and "not medical advice" not in ov.lower():
            s["footer"] = text_card("Educational only - not medical advice.", "Arial", int(30 * K), "shadow",
                                    int(900 * K))
        if ov and not (captions and _same(ov, s.get("voiceover", ""))):
            hook = i == 0 and not poetic
            s["ov_img"] = text_card(ov, "Arial Black" if hook else g["font"], int((60 if hook else 56) * K),
                                    "box" if hook else "shadow", int(900 * K))
        desky = s.get("visual") in ("page", "flip", "cover")
        s["ov_y"] = H * (0.13 if desky else 0.17)
        s["cap_y"] = H * (0.77 if desky else 0.64)
    cap = Captions(words, g["caption_font"], accent, g["caption_font"] == "Arial Black") if captions and words else None

    sfx_clips = []
    if page_sound:
        for si, s in enumerate(scenes):
            for k, (ft, fd) in enumerate(getattr(s["src"], "flip_events", [])):
                sfx_clips.append((sfx.page_turn(fd, variant=si * 3 + k), s["start"] + ft))

    # draw + encode every scene as its own segment, two at a time (Pillow releases the GIL while it works)
    bounds = [int(round(sc["start"] * FPS)) for sc in scenes] + [int(round(total * FPS))]
    n_frames = bounds[-1]
    done = [0]
    lock = threading.Lock()
    t_draw = time.time()

    def tick():
        with lock:
            done[0] += 1
            if done[0] % 15 == 0:
                left = (time.time() - t_draw) / done[0] * (n_frames - done[0])
                eta = f"about {left / 60:.0f} min left" if left > 90 else f"about {max(5, round(left, -1)):.0f} s left"
                progress(f"Drawing the video · {100 * done[0] // n_frames}% · {eta}", 0.3 + 0.62 * done[0] / n_frames)

    segs = [out_dir / f"seg_{i:02d}.mp4" for i in range(len(scenes))]
    # the free web server has little memory: one scene at a time there; two on a PC
    workers = int(os.getenv("RENDER_WORKERS", "0")) or (1 if os.name != "nt" else max(1, min(2, (os.cpu_count() or 2) // 2)))
    with ThreadPoolExecutor(workers) as pool:
        jobs = [pool.submit(_segment, sc, i, bounds[i], bounds[i + 1], cap.for_scene(i) if cap else None, segs[i], tick)
                for i, sc in enumerate(scenes)]
        for j in jobs:
            j.result()

    final_check = None
    if quality_check:
        final_check = _look_through(book, scenes, segs, bounds, cap, desk, assets, warn, progress, make)

    silent = out_dir / "video_only.mp4"
    lst = out_dir / "segments.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in segs), encoding="utf-8")
    ff.run(["-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", silent.name], cwd=out_dir)
    for p in [*segs, lst]:
        p.unlink(missing_ok=True)

    progress("Mixing voice, music and sound...", 0.95)
    final = out_dir / "final.mp4"
    mix_audio(silent, clips, sfx_clips, music, music_volume, total, final)
    silent.unlink(missing_ok=True)

    meta = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "book": book["id"], "variant": {k: v for k, v in variant.items()},
        "timeline": [{k: s[k] for k in ("beat", "visual", "start", "dur") if k in s} for s in scenes],
        "seconds": round(total, 2), "voice": voice_name or g["voice"], "captions": captions,
        "music": music.name if music else None, "cost": round(budget.spent_this_month() - spent_before, 4),
        "warnings": warnings, "file": final.name,
        "quality": {"shots": qa_reports, "final": final_check} if quality_check else None,
        "options": options, "draft": draft, "redo_of": redo_of,
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


def redo_scene(book: dict, render_dir: str, scene: int, prompt: str = "", progress=lambda m, f=None: None) -> Path:
    """Make a new version of a video with one scene re-made. Everything else (voice, other AI shots) is reused
    from the cache, so only the changed scene costs money."""
    meta = json.loads((Path(render_dir) / "render.json").read_text(encoding="utf-8"))
    variant = json.loads(json.dumps(meta["variant"]))
    s = variant["scenes"][scene]
    prompt = prompt.strip()
    if s.get("visual") == "stock":
        if prompt and prompt != s.get("stock_query"):
            s["stock_query"] = prompt
        else:
            s["_stock_skip"] = s.get("_stock_skip", 0) + 1       # same search: take the next clip
    elif prompt:
        s["prompt"] = prompt
    s["_take"] = s.get("_take", 0) + 20                          # always a fresh AI shot
    variant["name"] = (meta["variant"].get("name") or "video").split(" · redo")[0] + f" · redo {scene + 1}"
    opts = dict(meta.get("options") or {"voice_name": meta.get("voice"), "captions": meta.get("captions", True)})
    if opts.get("music"):
        opts["music"] = Path(opts["music"]) if Path(opts["music"]).exists() else None
    return render(book, variant, progress=progress, redo_of=Path(render_dir).name, **opts)


def delete_render(render_dir: str) -> None:
    """Remove a video (and its cloud copy)."""
    import shutil
    from . import storage
    d = Path(render_dir)
    if d.exists():
        shutil.rmtree(d)
    storage.delete_remote_folder(d)

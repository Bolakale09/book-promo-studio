"""UGC style: videos that feel filmed on a phone by a real reader, not produced by a studio.

Two halves: the SCRIPT (casual first-person voice, reaction-led, jump-cut pacing) and the LOOK (handheld sway,
punch-in jump cuts, phone-camera colour, grain, soft vignette). Both are applied only when UGC is chosen.
"""
import math
import random

import numpy as np
from PIL import Image, ImageChops

STYLES = {"polished": "🎬 Polished", "ugc": "📱 UGC (real person)"}

SCRIPT_RULES = """UGC STYLE (user-generated content) - this must NOT feel like an ad:
- Write like a real reader sending a voice note to a friend: first person, contractions, casual words, the odd
  "okay so", "no because", "I'm not kidding", "wait". Imperfect on purpose. Never marketing words (unleash, captivating,
  masterpiece, must-read, game-changer).
- Structure: (1) a reaction or confession hook ("I wasn't ready for this book", "I finished it at 3am and I'm not okay"),
  (2) ONE honest, specific reaction (what it did to you), (3) proof - a real line/page, (4) who it's for, in a plain
  sentence ("if you like X, you need this"), (5) a casual breadcrumb ("it's called {title} - go look it up").
- Short, quick scenes: 1.5-3 seconds each, 7-11 scenes, a new shot every line (jump-cut rhythm).
- Overlays: lowercase, casual, like text typed on a phone (max 7 words). No hashtags in overlays.
- Visuals: favour everyday real-life shots - hands holding the book, reading in bed, cosy couch, coffee, a bookshelf,
  turning pages - using stock footage, the real pages and the real cover. At most one AI shot, and it must look like a
  phone photo of a real room, never cinematic.
- post_caption: casual, lowercase, like a friend's post, ends with a soft prompt to comment or save."""

VOICE = ("Casual and real, like a friend telling you about a book they just finished on a voice note. Natural, "
         "slightly fast pace, small pauses and reactions, a hint of a smile. Not a performance, not an announcer.")

PHOTO_SUFFIX = (" Authentic user-generated phone footage look: shot handheld on a smartphone, natural window light, "
                "casual slightly imperfect framing, lived-in real room, soft phone-camera colour, no studio lighting, "
                "no cinematic grading, no text.")


def _lut(r: float, g: float, b: float, contrast: float, lift: int) -> list[int]:
    out = []
    for gain in (r, g, b):
        for v in range(256):
            x = ((v - 128) * contrast + 128) * gain
            out.append(int(min(255, max(0, x * (255 - lift) / 255 + lift))))
    return out


class PhoneLook:
    """Applied to the picture only (never to captions): a handheld phone-camera feel. Built once per video."""

    def __init__(self, w: int, h: int, seed: int = 0, fps: int = 30):
        self.w, self.h, self.fps = w, h, fps
        rnd = random.Random(seed)
        self.phase = [rnd.uniform(0, 6.28) for _ in range(6)]
        self.lut = _lut(1.03, 1.0, 0.95, 0.94, 7)  # warm, a little flat, blacks lifted like a phone video
        ys, xs = np.mgrid[0:h // 8, 0:w // 8]
        d = np.sqrt(((xs / (w / 8) - 0.5) * 1.15) ** 2 + ((ys / (h / 8) - 0.5) * 0.8) ** 2)
        v = (255 - 70 * np.clip(d - 0.28, 0, 1) ** 1.6 * 2.2).clip(150, 255).astype("uint8")
        self.vignette = Image.fromarray(v).resize((w, h), Image.BILINEAR).convert("RGB")
        gen = np.random.default_rng(seed)
        self.grain = [Image.fromarray((128 + gen.normal(0, 7, (h // 2, w // 2, 1)).repeat(3, 2)).clip(0, 255)
                                      .astype("uint8")).resize((w, h), Image.BILINEAR) for _ in range(5)]

    def __call__(self, frame: Image.Image, t: float, scene: int = 0) -> Image.Image:
        w, h = self.w, self.h
        # jump-cut punch-in on every other shot, plus slow "breathing" and a handheld sway
        zoom = (1.0 if scene % 2 == 0 else 1.1) + 0.035 + 0.012 * math.sin(t * 0.9 + self.phase[0])
        sway = w * 0.006
        dx = sway * (math.sin(t * 2.3 + self.phase[1]) + 0.5 * math.sin(t * 5.1 + self.phase[2]))
        dy = sway * (math.sin(t * 1.7 + self.phase[3]) + 0.5 * math.sin(t * 4.3 + self.phase[4]))
        bw, bh = w / zoom, h / zoom
        x0 = min(max((w - bw) / 2 + dx, 0), w - bw)
        y0 = min(max((h - bh) / 2 + dy, 0), h - bh)
        img = frame.resize((w, h), Image.BILINEAR, box=(x0, y0, x0 + bw, y0 + bh)).point(self.lut)
        img = ImageChops.multiply(img, self.vignette)
        return ImageChops.add(img, self.grain[int(t * self.fps) % len(self.grain)], 1.0, -128)

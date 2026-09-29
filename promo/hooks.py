"""Hook testing. The first two seconds decide whether anyone watches, so hooks are tested before you spend money
rendering them: a panel of imagined viewers (built from your book's target readers) scores each hook, and after
scripts are written the strongest untried hook can replace a weaker one automatically.

The scores are an AI's opinion, not real viewers - use them to drop the weak hooks, then let real views (Results)
decide. Hooks that got real views are shown to the panel as calibration.
"""
import json
import random
import time

from . import config, llm
from .genres import GENRES

WEIGHTS = {"stop": 0.40, "curiosity": 0.20, "clarity": 0.15, "emotion": 0.15, "fit": 0.10}
LABELS = {"stop": "Stops the scroll", "curiosity": "Curiosity", "clarity": "Clear at a glance",
          "emotion": "Emotion", "fit": "Fits the book"}
HOOK_TYPES = ["bold claim", "curiosity gap", "POV", "contrarian", "identity", "question"]
DEFAULT_MARGIN = 1.0

PANEL_SYSTEM = """You are a panel of five short-video viewers who love this kind of book. You scroll fast and
decide in under two seconds. You are honest, hard to impress, and you dislike salesy, clickbait or cringe hooks.
Respond with JSON only."""


def hook_of(variant: dict) -> dict:
    sc = (variant.get("scenes") or [{}])[0]
    return {"overlay": (sc.get("overlay") or "").strip(), "voiceover": (sc.get("voiceover") or "").strip(),
            "hook_type": variant.get("hook_type", "")}


def hook_text(h: dict) -> str:
    return h.get("overlay") or h.get("voiceover") or ""


def _context(book: dict) -> str:
    d = book.get("digest") or {}
    return (f"Book: {book['title']} ({GENRES[book['genre']]['label']})\nBlurb: {book.get('blurb') or '-'}\n"
            f"Who reads it: {d.get('target_readers') or book.get('audience') or '-'}\n"
            f"Feeling it promises: {d.get('emotional_promise') or '-'}\nTropes: {d.get('tropes_or_hooks') or '-'}")


def past_results(book_id: str) -> tuple[list[str], list[str]]:
    """(hooks that got the most views, hooks that got the fewest) from videos with logged views."""
    from . import render
    rows = []
    for r in render.list_renders(book_id):
        v = r.get("views")
        h = hook_text(hook_of(r.get("variant") or {}))
        if h and isinstance(v, (int, float)) and v > 0:
            rows.append((v, h))
    rows.sort(reverse=True)
    if len(rows) < 2:
        return [], []
    k = min(3, len(rows) // 2)
    return [h for _, h in rows[:k]], [h for _, h in rows[-k:]]


def candidates(book: dict, n: int = 8, avoid: list[str] | None = None, winners: list[str] | None = None) -> list[dict]:
    g = GENRES[book["genre"]]
    extra = ""
    if winners:
        extra += f"\nHooks that already did well for this book (write in a similar spirit, don't copy): {json.dumps(winners)}"
    if avoid:
        extra += f"\nDo not repeat or lightly reword any of these: {json.dumps(avoid[:30])}"
    user = f"""{_context(book)}
Tone: {g['tone']}
Example hooks for this genre (style only): {json.dumps(g['hook_examples'])}{extra}

Write {n} different hooks for a faceless 20-40 second promo video. Each has:
- "overlay": the on-screen hook text, max 9 words
- "voiceover": what the narrator says in the first 2 seconds (4-14 words, natural speech)
- "hook_type": one of {HOOK_TYPES}
Use a mix of hook types. No hashtags, no emojis, no "buy now", no fake claims about the book.
Return JSON: {{"hooks": [{{"overlay": "...", "voiceover": "...", "hook_type": "..."}}]}}"""
    out = llm.chat_json("You write scroll-stopping hooks for book promo videos. Respond with JSON only.", user,
                        max_out=1200 + 160 * n, what=f"{n} hook ideas")
    seen, hooks = {(a or "").lower() for a in (avoid or [])}, []
    for h in out.get("hooks", []):
        ov, vo = str(h.get("overlay", "")).strip(), str(h.get("voiceover", "")).strip()
        if (ov or vo) and (ov or vo).lower() not in seen:
            seen.add((ov or vo).lower())
            hooks.append({"overlay": ov or vo, "voiceover": vo or ov,
                          "hook_type": h.get("hook_type") if h.get("hook_type") in HOOK_TYPES else ""})
    return hooks[:n]


def _panel_pass(book: dict, hooks: list[dict], order: list[int], winners: list[str], losers: list[str]) -> dict[int, dict]:
    calib = ""
    if winners:
        calib = (f"\nCalibration from real results for this book. Hooks that got many views: {json.dumps(winners)}. "
                 f"Hooks that got few views: {json.dumps(losers)}. Let this shape what you reward.")
    listing = [{"id": i, "on_screen": hooks[i].get("overlay", ""), "spoken": hooks[i].get("voiceover", "")}
               for i in order]
    user = f"""{_context(book)}{calib}

Score each hook 0-10 on: stop (would you stop scrolling?), curiosity (do you need to know what comes next?),
clarity (understood in two seconds), emotion (do you feel something?), fit (does it honestly match this book
and its readers?). Be discriminating - use the whole range and give different hooks different scores.
"cringe": true if it is salesy, clickbait, cliched or embarrassing. "note": max 12 words on the main reason.

HOOKS:
{json.dumps(listing)}

Return JSON: {{"scores": [{{"id": 0, "stop": 0, "curiosity": 0, "clarity": 0, "emotion": 0, "fit": 0,
"cringe": false, "note": ""}}]}}"""
    out = llm.chat_json(PANEL_SYSTEM, user, max_out=600 + 130 * len(hooks), what=f"score {len(hooks)} hooks")
    res = {}
    for r in out.get("scores", []):
        try:
            res[int(r["id"])] = r
        except (KeyError, ValueError, TypeError):
            continue
    return res


def _num(x) -> float:
    try:
        return min(10.0, max(0.0, float(x)))
    except (TypeError, ValueError):
        return 5.0


def score(book: dict, hooks: list[dict], passes: int = 2, winners: list[str] | None = None,
          losers: list[str] | None = None) -> list[dict]:
    """Score hooks; returns them (same order) with "score" (0-10), "sub" (per-criterion) and "note".
    Each pass shows the hooks in a different order and the results are averaged, which cancels position bias."""
    if not hooks:
        return []
    if winners is None:
        winners, losers = past_results(book["id"])
    rng = random.Random(len(hooks) * 7919 + len(hook_text(hooks[0])))
    runs = []
    for k in range(passes):
        order = list(range(len(hooks)))
        if k:
            rng.shuffle(order)
        try:
            runs.append(_panel_pass(book, hooks, order, winners, losers or []))
        except Exception:
            if not runs and k == passes - 1:
                raise
    out = []
    for i, h in enumerate(hooks):
        got = [r[i] for r in runs if i in r]
        if not got:
            out.append({**h, "score": None, "sub": {}, "note": "not scored"})
            continue
        sub = {c: round(sum(_num(g.get(c)) for g in got) / len(got), 1) for c in WEIGHTS}
        base = sum(sub[c] * w for c, w in WEIGHTS.items())
        cringe = sum(1 for g in got if g.get("cringe")) / len(got)
        note = next((str(g.get("note", "")) for g in got if g.get("note")), "")
        out.append({**h, "score": round(max(0.0, base - 1.5 * cringe), 1), "sub": sub, "cringe": cringe >= 0.5,
                    "note": note[:110]})
    return out


def _swap_in(variant: dict, cand: dict) -> None:
    """Replace a script's hook. A page/flip opening keeps its spoken line (it reads the highlighted text)."""
    sc = variant["scenes"][0]
    sc["overlay"] = cand["overlay"]
    if sc.get("visual") not in ("page", "flip"):
        sc["voiceover"] = cand["voiceover"]
    if cand.get("hook_type"):
        variant["hook_type"] = cand["hook_type"]


def auto_swap(book: dict, variants: list[dict], n_cand: int = 8, margin: float = DEFAULT_MARGIN,
              progress=lambda m: None) -> int:
    """Test every script's own hook against fresh candidates; swap in a clearly better one. Records the result on
    each script (`hook_test`) so the change can be undone. Returns how many hooks were replaced."""
    variants = [v for v in variants if v.get("scenes")]
    if not variants:
        return 0
    winners, losers = past_results(book["id"])
    own = [hook_of(v) for v in variants]
    progress("Thinking up alternative hooks...")
    cands = candidates(book, n_cand, avoid=[hook_text(h) for h in own], winners=winners)
    progress("Testing the hooks on a panel of viewers...")
    scored = score(book, own + cands, 2, winners, losers)
    own_s, cand_s = scored[:len(own)], sorted((c for c in scored[len(own):] if c["score"] is not None),
                                              key=lambda c: -c["score"])
    stamp = time.strftime("%Y-%m-%d %H:%M")
    swapped, used = 0, set()
    for v, h in zip(variants, own_s):
        v["hook_test"] = {"score": h["score"], "note": h.get("note", ""), "tested": stamp, "swapped": False}
        if h["score"] is None:
            continue
        k = next((k for k, c in enumerate(cand_s) if k not in used and c["score"] >= h["score"] + margin), None)
        if k is None:
            continue
        used.add(k)
        best = cand_s[k]
        v["hook_test"].update({"score": best["score"], "note": best.get("note", ""), "swapped": True,
                               "original": {"overlay": h["overlay"], "voiceover": h["voiceover"],
                                            "hook_type": h["hook_type"], "score": h["score"]}})
        _swap_in(v, best)
        swapped += 1
    return swapped


def undo_swap(variant: dict) -> bool:
    ht = variant.get("hook_test") or {}
    o = ht.get("original")
    if not (ht.get("swapped") and o):
        return False
    _swap_in(variant, o)
    variant["hook_test"] = {"score": o.get("score"), "note": "", "tested": ht.get("tested"), "swapped": False}
    return True


# ---- the Hook lab: saved test results ----------------------------------------------------

def _lab_file(book_id: str):
    d = config.PROJECTS_DIR / book_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "hooks.json"


def load_lab(book_id: str) -> list[dict]:
    try:
        return json.loads(_lab_file(book_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_lab(book_id: str, rows: list[dict]) -> None:
    _lab_file(book_id).write_text(json.dumps(rows, indent=1), encoding="utf-8")


def run_lab(book: dict, n: int = 8, custom: list[str] | None = None, progress=lambda m: None) -> int:
    """Generate n new hooks and/or score your own; everything is added to the lab, best first."""
    rows = load_lab(book["id"])
    have = {hook_text(r).lower() for r in rows}
    winners, losers = past_results(book["id"])
    new = []
    for t in custom or []:
        t = t.strip()
        if t and t.lower() not in have:
            new.append({"overlay": t, "voiceover": t, "hook_type": "", "source": "yours"})
    if n:
        progress("Thinking up hooks...")
        for h in candidates(book, n, avoid=sorted(have), winners=winners):
            new.append({**h, "source": "ai"})
    if not new:
        return 0
    progress("Testing the hooks on a panel of viewers...")
    stamp = time.strftime("%Y-%m-%d %H:%M")
    scored = [{**s, "tested": stamp} for s in score(book, new, 2, winners, losers)]
    rows = sorted(scored + rows, key=lambda r: -(r.get("score") or 0))[:80]
    save_lab(book["id"], rows)
    return len(scored)

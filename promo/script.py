"""Write video scripts for the book from a blueprint + genre preset + book digest."""
import json

from . import book as bk, llm
from .genres import FIVE_RULES, GENRES

VISUAL_TYPES = {
    "page": "a real page of the manuscript lying open on a desk: the previous page turns over, then the quote is "
            "swept with a highlighter while the camera pushes in (FREE)",
    "flip": "fast page-to-page flip through several manuscript pages that lands on the quote page and highlights it "
            "(FREE) - great for hooks and 'proof' beats",
    "cover": "3D mockup of the book cover on the desk (FREE) - always the final breadcrumb scene",
    "stock": "real stock footage from Pexels found by 'stock_query' (FREE, very realistic)",
    "broll": "one of the author's own uploaded clips (FREE)",
    "character": "photorealistic AI photo of a named book character in a moment from the story (~$0.015)",
    "ai_image": "photorealistic AI photo of a scene/place/object, no named character (~$0.015)",
    "ai_video": "photorealistic AI video clip with real motion (~$0.07 per second - use for the hook or climax only)",
}

SCRIPT_SYSTEM = """You are a top BookTok / Bookstagram creative director who writes faceless short-form videos that
sell books without sounding like ads. You write in natural spoken English, short punchy lines, one idea per
scene. You follow the given blueprint's STRUCTURE and PACING but write completely original words for this
book. Respond with JSON only."""

SCENE_SHAPE = """{
  "beat": "Hook | Feeling | Proof | Payoff | Breadcrumb ...",
  "voiceover": "what the narrator says in this scene (natural speech, 4-16 words; empty string only if blueprint is text-only)",
  "overlay": "short on-screen text, max 9 words (can differ from voiceover; the hook overlay is the most important text in the video)",
  "visual": "page | flip | cover | stock | broll | character | ai_image | ai_video",
  "page": 12,                       // only for visual=page/flip: page number from the quote list
  "highlight": "verbatim quote",    // only for visual=page/flip: EXACT text copied from the quote list
  "character": "Name",             // only for visual=character
  "prompt": "photorealistic shot description: subject, action, setting, lighting, camera (for character/ai_image/ai_video)",
  "stock_query": "2-4 word Pexels search (for visual=stock)",
  "seconds": 3.0                    // target length if there is no voiceover
}"""


def _book_context(book: dict) -> str:
    d = book.get("digest") or {}
    chars = book.get("characters") or []
    quotes = d.get("quotes", [])[:20]
    featured = book.get("featured") or []
    return f"""BOOK
Title: {book['title']}
Author: {book.get('author') or '-'}
Genre: {GENRES[book['genre']]['label']}
Blurb: {book.get('blurb') or '-'}
Audience: {book.get('audience') or '-'}
Where to buy: {book.get('where_to_buy') or 'Amazon'}
Summary: {d.get('summary', '-')}
Emotional promise: {d.get('emotional_promise', '-')}
Target readers: {d.get('target_readers', '-')}
Tropes / hooks: {d.get('tropes_or_hooks', '-')}
Comparable books: {d.get('comparable_books', '-')}
Visual world: {d.get('visual_world', '-')}
Characters you may show (use exact names): {json.dumps([{'name': c['name'], 'description': c.get('description', '')} for c in chars]) if chars else 'none - do not use visual=character'}
Pages/lines the AUTHOR picked (use these first for page/flip scenes): {json.dumps(featured) if featured else '-'}
Quotes from the manuscript (page + verbatim text): {json.dumps(quotes) if (quotes or featured) else 'no manuscript - do not use visual=page or flip'}"""


def allowed_visuals(book: dict, max_ai_video: int = 1, has_broll: bool = False, has_stock: bool = True,
                    free_only: bool = False) -> dict:
    allowed = dict(VISUAL_TYPES)
    if not has_broll:
        allowed.pop("broll")
    if not has_stock:
        allowed.pop("stock")
    if max_ai_video <= 0 or free_only:
        allowed.pop("ai_video")
    if free_only:
        allowed.pop("ai_image")
        allowed.pop("character")
    if not book.get("characters"):
        allowed.pop("character", None)
    if not ((book.get("digest") or {}).get("quotes") or book.get("featured")) or not book.get("manuscript"):
        allowed.pop("page")
        allowed.pop("flip")
    return allowed


def generate(book: dict, blueprint: dict, n: int = 5, max_ai_video: int = 1, notes: str = "",
             has_broll: bool = False, has_stock: bool = True, focus_characters: list[str] | None = None,
             focus_pages: list[dict] | None = None, free_only: bool = False) -> list[dict]:
    g = GENRES[book["genre"]]
    allowed = allowed_visuals(book, max_ai_video, has_broll, has_stock, free_only)
    focus = ""
    if focus_characters and "character" in allowed:
        focus += ("\n- FEATURE THESE CHARACTERS (use visual=character or ai_video with \"character\" set, exact names): "
                  f"{json.dumps(focus_characters)}. Every variant must show at least one of them.")
    if focus_pages and "page" in allowed:
        focus += ("\n- SHOW THESE PAGES (visual=page or flip, copy page + highlight exactly): "
                  f"{json.dumps(focus_pages)}. Every variant must include at least one of them.")

    bp = {k: v for k, v in blueprint.items() if k not in ("transcript", "created")}
    user = f"""{_book_context(book)}

GENRE PLAYBOOK ({g['label']})
Angles that work: {json.dumps(g['angles'])}
Example hooks (style only, don't copy): {json.dumps(g['hook_examples'])}
Tone: {g['tone']}
Genre rules: {g['rules']}
Preferred visuals, in order: {g['visual_mix']}
Target length: ~{g['target_seconds']}s, {g['scene_seconds'][0]}-{g['scene_seconds'][1]}s per scene

BLUEPRINT TO FOLLOW (structure, pacing, hook mechanic, ending - NOT its words):
{json.dumps(bp)[:6000]}

THE 5 RULES:
{FIVE_RULES}

VISUAL TYPES YOU MAY USE:
{json.dumps(allowed, indent=1)}
- Use at most {max_ai_video} ai_video scene(s) per variant{' (put it on the hook)' if max_ai_video else ''}.
- Include at least one 'page' or 'flip' scene when quotes are available - showing the real page is the proof.
  For page/flip scenes the voiceover should read the highlighted line (or its key part) while it is highlighted.{focus}
- The LAST scene must be visual=cover with the breadcrumb overlay (e.g. "{g['breadcrumb'].format(title=book['title'])}").
- Prompts must be photorealistic (real people, natural light, shot on phone/35mm), vertical 9:16 framing,
  no text or logos in the image.
{('EXTRA NOTES FROM THE AUTHOR: ' + notes) if notes else ''}

Write {n} DIFFERENT variants, each using a different angle and hook type. Return JSON:
{{"variants": [{{
  "name": "short label",
  "angle": "which angle",
  "hook_type": "bold claim | curiosity gap | POV | contrarian | identity | question",
  "scenes": [{SCENE_SHAPE}],
  "post_caption": "TikTok caption, 1-2 lines, curiosity + soft breadcrumb",
  "hashtags": ["#booktok", "..."],
  "why_it_will_work": "one sentence"
}}]}}"""
    out = llm.chat_json(SCRIPT_SYSTEM, user, max_out=4000 + 2200 * n, what=f"{n} script variants")
    variants = out.get("variants", [])
    for v in variants:
        _clean(book, v, allowed)
    return variants


def _clean(book: dict, v: dict, allowed: dict) -> None:
    """Fix common model slips so rendering never fails."""
    scenes = v.get("scenes") or []
    names = {c["name"].lower(): c["name"] for c in book.get("characters", [])}
    quotes = (book.get("featured") or []) + ((book.get("digest") or {}).get("quotes") or [])
    for i, s in enumerate(scenes):
        s.setdefault("voiceover", "")
        s.setdefault("overlay", "")
        vis = s.get("visual", "stock")
        if vis not in allowed:
            fallbacks = (["ai_image"] if vis in ("character", "ai_video") else []) + ["stock", "page", "cover"]
            vis = next(f for f in fallbacks if f in allowed or f == "cover")
            if vis == "page" and quotes and not s.get("highlight"):
                q = quotes[i % len(quotes)]
                s["page"], s["highlight"] = q.get("page"), q.get("text", "")
            if vis == "stock" and not s.get("stock_query"):
                s["stock_query"] = " ".join((s.get("prompt") or "reading a book").split()[:4])
        if vis == "character" and (s.get("character") or "").lower() not in names:
            vis = "ai_image"
        if vis in ("character", "ai_video") and (s.get("character") or "").lower() in names:
            s["character"] = names[s["character"].lower()]
        else:
            s.pop("character", None)
        if vis in ("page", "flip"):
            s["page"] = bk.find_quote_page(book, s.get("highlight", ""), s.get("page")) or 1
        s["visual"] = vis
    if not scenes or scenes[-1]["visual"] != "cover":
        g = GENRES[book["genre"]]
        scenes.append({"beat": "Breadcrumb", "voiceover": "", "visual": "cover", "seconds": 3.0,
                       "overlay": g["breadcrumb"].format(title=book["title"])})
    v["scenes"] = scenes


def variations(book: dict, winner: dict, change: str, n: int = 3) -> list[dict]:
    """Rule 5: clone a winner, changing ONE thing (hook, footage, pacing, angle wording)."""
    user = f"""{_book_context(book)}

This video script is a WINNER (it performed well). Make {n} variations that keep everything the same EXCEPT: {change}.
Keep the same JSON shape, same number of scenes and same ending.

WINNER:
{json.dumps(winner)[:8000]}

Return JSON: {{"variants": [ ... ]}}"""
    out = llm.chat_json(SCRIPT_SYSTEM, user, max_out=3000 + 2000 * n, what=f"{n} variations ({change})")
    allowed = allowed_visuals(book, max_ai_video=1, has_broll=True, has_stock=True)
    variants = out.get("variants", [])
    for v in variants:
        _clean(book, v, allowed)
    return variants


# ---- saved scripts ------------------------------------------------------------------------

def _store(book_id: str):
    from . import config
    d = config.PROJECTS_DIR / book_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "scripts.json"


def load_scripts(book_id: str) -> list[dict]:
    p = _store(book_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save_scripts(book_id: str, scripts: list[dict]) -> None:
    _store(book_id).write_text(json.dumps(scripts, indent=1), encoding="utf-8")


def add_scripts(book_id: str, variants: list[dict], source: str) -> None:
    from datetime import datetime
    scripts = load_scripts(book_id)
    stamp = datetime.now().strftime("%m-%d %H:%M")
    for v in variants:
        v["id"] = f"{datetime.now():%Y%m%d%H%M%S%f}"[:18] + str(len(scripts))
        v["created"] = stamp
        v["source"] = source
        scripts.insert(0, v)
    save_scripts(book_id, scripts)

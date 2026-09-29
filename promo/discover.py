"""Find viral videos for a keyword, and turn what you find into ideas.

Be honest about the sources - TikTok and Instagram have no free public search, and scraping them breaks their
terms and their login walls. So results come from whichever of these you have set up, and the page says which ran:

  apify     APIFY_TOKEN in .env  - real TikTok / Instagram search with view counts (paid by Apify, ~$1-3 per 1,000 videos)
  grok      XAI_API_KEY          - Grok's live web + X search finds public video links (about $0.05 a search)
  youtube   free, no key         - YouTube Shorts search with real view counts (same book-video trends, other platform)
  paste     always               - paste any link you found yourself; the app fills in the title and thumbnail

"Copy this style" downloads the video and builds a blueprint (structure only - never its words), exactly like the
Format page. The idea board is written from your book plus what was found.
"""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

from . import analyze, config, ingest, llm
from .genres import GENRES

TIKTOK_RE = re.compile(r"https?://(?:www\.|vm\.|vt\.|m\.)?tiktok\.com/[^\s\"'<>)\]]+", re.I)
INSTA_RE = re.compile(r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p|tv)/[A-Za-z0-9_-]+/?", re.I)
YOUTUBE_RE = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:shorts/|watch\?v=)|youtu\.be/)[A-Za-z0-9_-]+", re.I)
MAX_SECONDS = 120  # book promos worth copying are short


def token(name: str) -> str:
    return os.getenv(name, "").strip()


def sources() -> dict[str, dict]:
    """Which search sources are usable right now."""
    return {
        "apify": {"label": "Apify (TikTok + Instagram, real view counts)", "ready": bool(token("APIFY_TOKEN")),
                  "how": "Add APIFY_TOKEN (apify.com, free trial credit)."},
        "grok": {"label": "Grok live search (TikTok + Instagram links)", "ready": bool(config.XAI_API_KEY),
                 "how": "Uses your XAI_API_KEY."},
        "youtube": {"label": "YouTube Shorts (free, real view counts)", "ready": True, "how": "Always available."},
    }


# ---- keywords & manual links -------------------------------------------------------------------

def platform_of(url: str) -> str:
    u = url.lower()
    if "tiktok.com" in u:
        return "TikTok"
    if "instagram.com" in u:
        return "Instagram"
    if "youtube.com" in u or "youtu.be" in u:
        return "YouTube"
    return "Other"


def suggest_keywords(book: dict) -> list[str]:
    """Search words worth trying: the title, the genre's community tag, and the book's tropes."""
    g = GENRES.get(book.get("genre"), {})
    out = [book.get("title", "").strip()]
    if g.get("label"):
        out.append(f"{g['label'].lower()} book recommendations")
    for tr in ((book.get("digest") or {}).get("tropes_or_hooks") or [])[:4]:
        out.append(f"{tr} books" if isinstance(tr, str) else "")
    out.append("booktok")
    seen, res = set(), []
    for k in out:
        k = " ".join(str(k).split())
        if k and k.lower() not in seen:
            seen.add(k.lower())
            res.append(k)
    return res


def search_links(keyword: str) -> list[tuple[str, str]]:
    """Open-in-browser searches, for when you want to look yourself (always works, no key needed)."""
    q = quote(keyword)
    tag = re.sub(r"[^a-z0-9]", "", keyword.lower())
    return [("TikTok search", f"https://www.tiktok.com/search/video?q={q}"),
            ("TikTok hashtag", f"https://www.tiktok.com/tag/{tag}" if tag else ""),
            ("Instagram hashtag", f"https://www.instagram.com/explore/tags/{tag}/" if tag else ""),
            ("YouTube Shorts", f"https://www.youtube.com/results?search_query={q}&sp=EgIYAQ%253D%253D")]


# ---- storage (per book) ------------------------------------------------------------------------

def _file(book_id: str) -> Path:
    d = config.PROJECTS_DIR / book_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "discover.json"


def load(book_id: str) -> dict:
    try:
        return json.loads(_file(book_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save(book_id: str, data: dict) -> None:
    _file(book_id).write_text(json.dumps(data, indent=1), encoding="utf-8")


def bp_id_for(url: str) -> str:
    return ingest.ref_id_for(url)


def studied(url: str) -> bool:
    return (config.BLUEPRINTS_DIR / f"{bp_id_for(url)}.json").exists()


# ---- providers ---------------------------------------------------------------------------------

def _num(*vals) -> int | None:
    for v in vals:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
        if isinstance(v, str) and v.replace(",", "").isdigit():
            return int(v.replace(",", ""))
    return None


def _apify(actor: str, body: dict, timeout: int = 150) -> list[dict]:
    import httpx
    r = httpx.post(f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
                   params={"token": token("APIFY_TOKEN")}, json=body, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def from_apify(keyword: str, limit: int = 20) -> list[dict]:
    out = []
    for it in _apify("clockworks~tiktok-scraper", {"searchQueries": [keyword], "resultsPerPage": limit,
                                                   "shouldDownloadVideos": False, "shouldDownloadCovers": False}):
        url = it.get("webVideoUrl") or it.get("url")
        if not url:
            continue
        out.append({"url": url, "platform": "TikTok", "title": (it.get("text") or "")[:200],
                    "author": (it.get("authorMeta") or {}).get("name", ""),
                    "views": _num(it.get("playCount")), "likes": _num(it.get("diggCount")),
                    "shares": _num(it.get("shareCount")), "seconds": _num((it.get("videoMeta") or {}).get("duration")),
                    "thumbnail": (it.get("videoMeta") or {}).get("coverUrl", ""), "source": "apify"})
    tag = re.sub(r"[^a-z0-9]", "", keyword.lower())
    if tag:
        try:
            for it in _apify("apify~instagram-hashtag-scraper", {"hashtags": [tag], "resultsType": "reels",
                                                                 "resultsLimit": limit}):
                url = it.get("url")
                if not url:
                    continue
                out.append({"url": url, "platform": "Instagram", "title": (it.get("caption") or "")[:200],
                            "author": it.get("ownerUsername", ""),
                            "views": _num(it.get("videoPlayCount"), it.get("videoViewCount")),
                            "likes": _num(it.get("likesCount")), "shares": None,
                            "seconds": _num(it.get("videoDuration")), "thumbnail": it.get("displayUrl", ""),
                            "source": "apify"})
        except Exception:
            pass  # Instagram is a bonus; TikTok results still count
    return out


def from_grok(keyword: str, limit: int = 12) -> list[dict]:
    """Grok searches the live web / X for public book videos. It only returns links; each one is checked after."""
    from . import budget
    model = token("XAI_SEARCH_MODEL") or "grok-4.3"
    budget.guard(0.08, "video search")
    prompt = (f"Find {limit} popular, public short book-promo videos on TikTok and Instagram Reels about: "
              f"{keyword}. Prefer videos with many views. Only give links you actually found - never invent one. "
              'Return JSON only: {"videos":[{"url":"full link","description":"one line","approx_views":"e.g. 1.2M or unknown"}]}')
    resp = llm.xai_client().responses.create(model=model, input=prompt,
                                             tools=[{"type": "web_search"}, {"type": "x_search"}])
    budget.record("chat", model, 0.05, "video search")
    text = getattr(resp, "output_text", "") or ""
    rows, seen = [], set()
    try:
        s, e = text.find("{"), text.rfind("}")
        for v in json.loads(text[s:e + 1]).get("videos", []):
            m = TIKTOK_RE.search(v.get("url", "")) or INSTA_RE.search(v.get("url", ""))
            if m and m.group(0) not in seen:
                seen.add(m.group(0))
                rows.append({"url": m.group(0), "platform": platform_of(m.group(0)),
                             "title": v.get("description", "")[:200], "author": "",
                             "views": _parse_views(v.get("approx_views")), "likes": None, "shares": None,
                             "seconds": None, "thumbnail": "", "source": "grok", "unverified": True})
    except (ValueError, AttributeError):
        pass
    for m in list(TIKTOK_RE.finditer(text)) + list(INSTA_RE.finditer(text)):  # links the JSON missed
        u = m.group(0).rstrip(".,;")
        if u not in seen:
            seen.add(u)
            rows.append({"url": u, "platform": platform_of(u), "title": "", "author": "", "views": None,
                         "likes": None, "shares": None, "seconds": None, "thumbnail": "", "source": "grok",
                         "unverified": True})
    return rows[:limit * 2]


def _parse_views(s) -> int | None:
    m = re.fullmatch(r"\s*~?([\d.,]+)\s*([kmb]?)\+?\s*(?:views)?\s*", str(s or "").lower())
    if not m:
        return None
    try:
        return int(float(m.group(1).replace(",", "")) * {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2)])
    except ValueError:
        return None


def from_youtube(keyword: str, limit: int = 15) -> list[dict]:
    import yt_dlp
    opts = {"quiet": True, "extract_flat": True, "skip_download": True, "noplaylist": False}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit * 2}:{keyword} book #shorts", download=False)
    out = []
    for e in (info or {}).get("entries") or []:
        dur = e.get("duration")
        if dur and dur > MAX_SECONDS:
            continue
        vid = e.get("id")
        if not vid:
            continue
        out.append({"url": f"https://www.youtube.com/shorts/{vid}", "platform": "YouTube",
                    "title": (e.get("title") or "")[:200], "author": e.get("channel") or e.get("uploader") or "",
                    "views": _num(e.get("view_count")), "likes": None, "shares": None, "seconds": _num(dur),
                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", "source": "youtube"})
    return out[:limit]


def enrich(item: dict, timeout: float = 8) -> dict | None:
    """Check a link is a real, public video and fill in title / author / thumbnail (TikTok's free oEmbed).
    Returns None for a TikTok link that no longer exists."""
    if item["platform"] != "TikTok":
        return item
    try:
        import httpx
        r = httpx.get("https://www.tiktok.com/oembed", params={"url": item["url"]}, timeout=timeout,
                      follow_redirects=True)
    except Exception:
        return item  # can't check right now - keep it, marked as unverified
    if r.status_code in (400, 404):
        return None
    if r.status_code == 200:
        try:
            d = r.json()
            item["title"] = item.get("title") or d.get("title", "")[:200]
            item["author"] = item.get("author") or d.get("author_name", "")
            item["thumbnail"] = item.get("thumbnail") or d.get("thumbnail_url", "")
            item.pop("unverified", None)
        except ValueError:
            pass
    return item


def add_link(url: str) -> dict:
    """A link you found yourself."""
    m = TIKTOK_RE.search(url) or INSTA_RE.search(url) or YOUTUBE_RE.search(url)
    if not m:
        raise ValueError("That doesn't look like a TikTok, Instagram or YouTube video link.")
    item = {"url": m.group(0).rstrip(".,;"), "platform": platform_of(m.group(0)), "title": "", "author": "",
            "views": None, "likes": None, "shares": None, "seconds": None, "thumbnail": "", "source": "you",
            "unverified": True}
    return enrich(item) or item


def search(keyword: str, progress=lambda m, f=None: None) -> tuple[list[dict], list[str]]:
    """Run every available source. Returns (videos best-first, notes about what ran / failed)."""
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("Type a keyword first.")
    notes, rows = [], []
    plan = [("apify", from_apify, "Searching TikTok + Instagram (Apify)"),
            ("grok", from_grok, "Asking Grok to search TikTok / Instagram"),
            ("youtube", from_youtube, "Searching YouTube Shorts")]
    live = [p for p in plan if sources()[p[0]]["ready"]]
    for i, (name, fn, msg) in enumerate(live):
        progress(msg + "...", 0.05 + 0.5 * i / max(1, len(live)))
        try:
            got = fn(keyword)
            notes.append(f"{sources()[name]['label']}: {len(got)} found")
            rows += got
        except Exception as e:
            notes.append(f"{sources()[name]['label']}: failed ({type(e).__name__}: {str(e)[:120]})")
    if not sources()["apify"]["ready"]:
        notes.append("Real TikTok / Instagram view counts need an Apify token (optional).")
    best: dict[str, dict] = {}
    for r in rows:  # the same video from two sources: keep the entry that knows more
        cur = best.get(r["url"])
        if cur is None or (r.get("views") or 0) > (cur.get("views") or 0):
            best[r["url"]] = {**(cur or {}), **{k: v for k, v in r.items() if v not in (None, "")}}
    uniq = list(best.values())
    checked = []
    for i, r in enumerate(uniq[:40]):
        progress(f"Checking links ({i + 1}/{min(len(uniq), 40)})...", 0.6 + 0.35 * i / max(1, min(len(uniq), 40)))
        r = enrich(r)
        if r:
            checked.append(r)
    checked.sort(key=lambda r: (r.get("views") is None, -(r.get("views") or 0)))
    return checked, notes


# ---- copy the style ----------------------------------------------------------------------------

def study(url: str, stats: dict | None = None, progress=lambda m, f=None: None) -> str:
    """Download the video and build its blueprint. Returns the blueprint id."""
    progress("Downloading the video...", 0.05)
    try:
        video = ingest.download(url)
    except Exception as e:
        hint = ""
        if platform_of(url) == "Instagram":
            hint = (" Instagram usually needs a login: set COOKIES_FILE in .env to an exported cookies.txt, or "
                    "download the video yourself and upload it on the Format page.")
        raise RuntimeError(f"Couldn't download it ({str(e)[:160]}).{hint}") from e
    bp = analyze.analyze_reference(video, progress=lambda m: progress(m, 0.4))
    bp_id = video.parent.name
    if stats:
        bp["reference_stats"] = {k: v for k, v in stats.items() if v is not None}
        analyze.save_blueprint(bp_id, bp)
    return bp_id


# ---- idea board --------------------------------------------------------------------------------

IDEA_SYSTEM = """You are a book-marketing strategist for TikTok, Reels and Shorts. You turn one book and a look at
what is working into fresh, ORIGINAL ideas. Never copy wording from other creators - borrow structures and angles
only. Be specific to this book, never generic. Respond with JSON only."""

IDEA_SHAPE = """{
  "hooks": [{"text": "first line, under 12 words", "type": "bold claim | curiosity gap | POV | contrarian | identity | question", "why": "short"}],   // 10
  "angles": [{"angle": "a way to sell this book", "first_line": "opening line", "why": "who it hits"}],   // 6
  "video_ideas": [{"title": "working title", "format": "e.g. POV, ranking, reading-list, reaction, myth-busting, before/after", "beats": "3-4 beats in one line"}],   // 6
  "hashtags": ["#..."],   // 15, mix of big, medium and niche
  "comparables": [{"title": "real book readers of this one also love", "author": "", "why": "short"}],   // 6
  "captions": ["ready-to-post caption with a soft call to action"],   // 4
  "trends": ["what the found videos have in common, one line each"]   // 3-5, [] if no videos were provided
}"""


def make_ideas(book: dict, keyword: str, videos: list[dict]) -> dict:
    d = book.get("digest") or {}
    seen = "\n".join(f"- {v.get('platform')}: {v.get('title') or '(no title)'} "
                     f"[{v.get('views') if v.get('views') is not None else 'views unknown'} views]"
                     for v in videos[:15]) or "(none found - work from the book and keyword alone)"
    user = f"""Book: {book.get('title')} by {book.get('author') or 'the author'} ({GENRES[book['genre']]['label']})
Blurb: {book.get('blurb') or '-'}
Readers: {d.get('target_readers') or book.get('audience') or '-'}
Promise: {d.get('emotional_promise') or '-'}
Tropes / angles: {d.get('tropes_or_hooks') or '-'}
Keyword being explored: {keyword}

Videos found for that keyword (titles and views only):
{seen}

Return this JSON (the // notes are counts, do not include them):
{IDEA_SHAPE}
Comparable books must be real, well-known titles - if you are not sure a book exists, leave it out."""
    return llm.chat_json(IDEA_SYSTEM, user, max_out=3500, what="idea board")


def run_search(book: dict, keyword: str, progress=lambda m, f=None: None, ideas: bool = True) -> dict:
    """The whole job: search, then (optionally) write the idea board from the results. Saves to the book."""
    rows, notes = search(keyword, progress)
    data = {"keyword": keyword, "videos": rows, "notes": notes, "searched": time.strftime("%Y-%m-%d %H:%M"),
            "ideas": (load(book["id"]).get("ideas") if not ideas else None)}
    save(book["id"], data)  # keep the videos even if the ideas step fails
    if ideas:
        progress("Writing the idea board...", 0.97)
        try:
            data["ideas"] = make_ideas(book, keyword, rows)
        except Exception as e:
            data["notes"].append(f"Idea board failed: {str(e)[:120]}")
        save(book["id"], data)
    return data

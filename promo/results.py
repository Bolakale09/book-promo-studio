"""Results dashboard: what you logged for each video (views, likes, ...) turned into totals and plain-language
lessons - which hooks, angles, looks and lengths perform for THIS book. Needs at least two videos per group before
it says anything, so a lucky video doesn't pass for a pattern."""
import math
from pathlib import Path

from . import llm, render, schedule

METRICS = ["views", "likes", "comments", "shares", "saves", "clicks", "sales"]
MIN_GROUP = 2


def _num(x) -> float | None:
    try:
        return None if x in (None, "") or (isinstance(x, float) and math.isnan(x)) else float(x)
    except (TypeError, ValueError):
        return None


def visual_look(variant: dict) -> str:
    kinds = {s.get("visual") for s in variant.get("scenes", [])}
    if kinds & {"page", "flip"}:
        return "Real book pages"
    if "ai_video" in kinds:
        return "AI video"
    if kinds & {"character", "ai_image"}:
        return "AI images"
    return "Stock and cover"


def length_band(seconds: float) -> str:
    return "Under 20 s" if seconds < 20 else "20-35 s" if seconds < 35 else "35 s or more"


def rows(book_id: str) -> list[dict]:
    """One row per finished video (not drafts) with its script traits and logged numbers."""
    slots = schedule.posted_slots(schedule.load(book_id))
    out = []
    for r in render.list_renders(book_id):
        if r.get("draft"):
            continue
        v = r.get("variant") or {}
        name = Path(r["dir"]).name
        sc0 = (v.get("scenes") or [{}])[0]
        row = {"dir": r["dir"], "id": name, "name": v.get("name") or name, "created": (r.get("created") or "")[:10],
               "seconds": r.get("seconds") or 0, "cost": r.get("cost") or 0.0, "winner": bool(r.get("winner")),
               "hook": (sc0.get("overlay") or sc0.get("voiceover") or "")[:70],
               "Hook type": v.get("hook_type") or "unknown", "Angle": v.get("angle") or "unknown",
               "Visuals": visual_look(v), "Length": length_band(r.get("seconds") or 0),
               "Narrator": "My own voice" if r.get("own_voice") else "AI voice",
               "hook_score": (v.get("hook_test") or {}).get("score")}
        wd, hr = slots.get(name, (None, None))
        row["Weekday"] = schedule.WEEKDAYS[wd] if wd is not None else None
        row["Hour"] = f"{hr:02d}:00" if hr is not None else None
        for m in METRICS:
            row[m] = _num(r.get(m))
        row["logged"] = row["views"] is not None
        eng = sum(row[m] or 0 for m in ("likes", "comments", "shares", "saves"))
        row["engagement"] = eng / row["views"] if row["views"] else None
        out.append(row)
    return out


def _sum(rs: list[dict], key: str) -> float:
    return sum(r[key] or 0 for r in rs)


def kpis(rs: list[dict]) -> dict:
    logged = [r for r in rs if r["logged"]]
    views = _sum(logged, "views")
    best = max(logged, key=lambda r: r["views"], default=None)
    cost = _sum(logged, "cost")
    eng = sum(_sum([r], "likes") + _sum([r], "comments") + _sum([r], "shares") + _sum([r], "saves") for r in logged)
    return {"made": len(rs), "logged": len(logged), "views": views,
            "avg_views": views / len(logged) if logged else 0.0, "best": best,
            "cost_per_1k": cost / (views / 1000) if views else None,
            "engagement": eng / views if views else None, "clicks": _sum(logged, "clicks"),
            "sales": _sum(logged, "sales"), "total_cost": _sum(rs, "cost")}


def groups(rs: list[dict], key: str) -> list[dict]:
    """Average views per value of `key` (e.g. hook type), most views first."""
    by: dict[str, list] = {}
    for r in rs:
        if r["logged"] and r.get(key):
            by.setdefault(r[key], []).append(r)
    out = [{"group": g, "n": len(v), "avg_views": _sum(v, "views") / len(v), "total_views": _sum(v, "views"),
            "avg_engagement": (sum(r["engagement"] or 0 for r in v) / len(v))} for g, v in by.items()]
    return sorted(out, key=lambda g: -g["avg_views"])


def insights(rs: list[dict]) -> list[str]:
    """Plain sentences, only where each side of a comparison has at least MIN_GROUP videos."""
    out = []
    for key in ("Hook type", "Angle", "Visuals", "Length", "Narrator", "Weekday", "Hour"):
        gs = [g for g in groups(rs, key) if g["n"] >= MIN_GROUP]
        if len(gs) < 2:
            continue
        top, low = gs[0], gs[-1]
        if low["avg_views"] <= 0 or top["avg_views"] / low["avg_views"] < 1.25:
            continue
        x = top["avg_views"] / low["avg_views"]
        out.append(f"{key}: \"{top['group']}\" averages {x:.1f}x the views of \"{low['group']}\" "
                   f"({top['avg_views']:,.0f} vs {low['avg_views']:,.0f}; {top['n']} and {low['n']} videos).")
    scored = [(r["hook_score"], r["views"]) for r in rs if r["logged"] and r.get("hook_score") is not None]
    if len(scored) >= 5:
        c = _pearson([a for a, _ in scored], [b for _, b in scored])
        if c is not None and abs(c) >= 0.4:
            out.append("Hook test scores " + ("do" if c > 0 else "do NOT") + f" track real views here (correlation {c:+.2f}"
                       f" over {len(scored)} videos) - " + ("trust them more." if c > 0 else "lean on real results instead."))
    return out


def _pearson(a: list, b: list) -> float | None:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def save_metrics(row_dir: str, **metrics) -> None:
    clean = {}
    for k, v in metrics.items():
        if k == "winner":
            clean[k] = bool(v)
        elif k in METRICS:
            n = _num(v)
            clean[k] = None if n is None else max(0, int(n))
    render.update_render(row_dir, **clean)


def coach(book: dict, rs: list[dict]) -> str:
    """Optional: ask the AI to read the table and suggest what to make next (a few cents)."""
    logged = [r for r in rs if r["logged"]]
    if len(logged) < 3:
        raise ValueError("Log the numbers for at least 3 videos first.")
    table = [{k: r[k] for k in ("hook", "Hook type", "Angle", "Visuals", "Length", "Narrator", "views", "likes",
                                "saves", "shares", "clicks", "sales")} for r in logged[:30]]
    out = llm.chat_json(
        "You are a practical social media coach for indie authors. Be concrete and honest; small samples mean "
        "weak evidence, so say so. Respond with JSON only.",
        f"Book: {book['title']}\nVideos and results: {table}\n"
        'Give 3-5 short, specific next steps (what to make more of, what to stop, what to test next). '
        'Return JSON: {"advice": ["..."]}', max_out=900, what="results coach")
    return "\n".join(f"- {a}" for a in out.get("advice", []))

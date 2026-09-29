"""Content calendar: which video goes out on which day, on which platform. Stored per book in calendar.json.
Best-time defaults are common starting points, not guarantees - your own Results show what works for your readers."""
import json
import re
import secrets
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

from . import config
from .kit import PLATFORMS

STATUSES = ["planned", "posted", "skipped"]
# Typical starting times (local): evenings and lunch breaks, when book readers scroll.
BEST_TIMES = {"TikTok": "19:00", "Instagram Reels": "12:00", "YouTube Shorts": "17:00"}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# which weekdays get a post for N posts a week (Mon = 0)
PATTERNS = {1: [2], 2: [1, 4], 3: [0, 2, 4], 4: [0, 1, 3, 5], 5: [0, 1, 2, 3, 4], 6: [0, 1, 2, 3, 4, 5], 7: list(range(7))}


def _file(book_id: str) -> Path:
    d = config.PROJECTS_DIR / book_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "calendar.json"


def load(book_id: str) -> list[dict]:
    try:
        rows = json.loads(_file(book_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return sorted(rows, key=lambda e: (e["date"], e["time"], e["platform"]))


def save(book_id: str, entries: list[dict]) -> None:
    _file(book_id).write_text(json.dumps(sorted(entries, key=lambda e: (e["date"], e["time"])), indent=1),
                              encoding="utf-8")


def _valid_time(t: str) -> str:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", (t or "").strip())
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        raise ValueError("Time must look like 19:00.")
    return f"{int(m[1]):02d}:{m[2]}"


def entry(render: str, title: str, day: date | str, at: str, platform: str, note: str = "") -> dict:
    if platform not in PLATFORMS:
        raise ValueError(f"Unknown platform: {platform}")
    d = day if isinstance(day, str) else day.isoformat()
    date.fromisoformat(d)
    return {"id": secrets.token_hex(4), "render": render, "title": title, "date": d, "time": _valid_time(at),
            "platform": platform, "status": "planned", "note": note, "url": ""}


def add(book_id: str, render: str, title: str, day: date | str, at: str, platform: str, note: str = "") -> dict:
    e = entry(render, title, day, at, platform, note)
    save(book_id, load(book_id) + [e])
    return e


def update(book_id: str, entry_id: str, **fields) -> None:
    rows = load(book_id)
    for e in rows:
        if e["id"] == entry_id:
            if "time" in fields:
                fields["time"] = _valid_time(fields["time"])
            if "date" in fields:
                date.fromisoformat(fields["date"])
            if "status" in fields and fields["status"] not in STATUSES:
                raise ValueError("Unknown status")
            e.update({k: v for k, v in fields.items() if k in e})
    save(book_id, rows)


def remove(book_id: str, entry_id: str) -> None:
    save(book_id, [e for e in load(book_id) if e["id"] != entry_id])


def when(e: dict) -> datetime:
    return datetime.fromisoformat(f"{e['date']}T{e['time']}")


def due(entries: list[dict], now: datetime | None = None) -> list[dict]:
    """Planned posts whose time has come."""
    now = now or datetime.now()
    return [e for e in entries if e["status"] == "planned" and when(e) <= now]


def upcoming(entries: list[dict], now: datetime | None = None, n: int = 3) -> list[dict]:
    now = now or datetime.now()
    return [e for e in entries if e["status"] == "planned" and when(e) > now][:n]


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def order_videos(renders: list[dict]) -> list[dict]:
    """Which videos to post first: marked winners, then the ones with most views, then the newest."""
    return sorted(renders, key=lambda r: (bool(r.get("winner")), r.get("views") or 0, r.get("created", "")),
                  reverse=True)


def plan(book_id: str, renders: list[dict], per_week: int = 3, weeks: int = 2, start: date | None = None,
         platforms: list[str] | None = None, times: dict | None = None, now: datetime | None = None) -> list[dict]:
    """Spread unscheduled videos over the next weeks. The same video goes out on every chosen platform that day.
    Returns the new entries (already saved)."""
    now = now or datetime.now()
    platforms = platforms or ["TikTok"]
    times = {**BEST_TIMES, **(times or {})}
    existing = load(book_id)
    used = {e["render"] for e in existing if e["status"] in ("planned", "posted")}
    pool = [r for r in order_videos(renders) if Path(r["dir"]).name not in used and not r.get("draft")]
    days = PATTERNS[max(1, min(7, per_week))]
    first = week_start(start or now.date())
    slots = []
    for w in range(max(1, weeks)):
        for wd in days:
            d = first + timedelta(days=7 * w + wd)
            if d >= (start or now.date()):
                slots.append(d)
    new = []
    for d, r in zip(slots, pool):
        name = Path(r["dir"]).name
        title = (r.get("variant") or {}).get("name") or name
        for p in platforms:
            e = entry(name, title, d, times[p], p)
            if when(e) < now and e["date"] == now.date().isoformat():
                e["date"] = (d + timedelta(days=1)).isoformat()
            new.append(e)
    save(book_id, existing + new)
    return new


def posted_slots(entries: list[dict]) -> dict[str, tuple[int, int]]:
    """render -> (weekday, hour) for videos that were posted exactly once (so results can be tied to a time)."""
    by: dict[str, list] = {}
    for e in entries:
        if e["status"] == "posted":
            by.setdefault(e["render"], []).append(e)
    return {r: (when(v[0]).weekday(), when(v[0]).hour) for r, v in by.items() if len(v) == 1}


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(entries: list[dict], book_title: str) -> str:
    """A calendar file (.ics) for Google/Apple/Outlook calendars, with a reminder 15 minutes before each post."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Book Promo Studio//EN", "CALSCALE:GREGORIAN"]
    for e in entries:
        if e["status"] != "planned":
            continue
        start = when(e)
        lines += ["BEGIN:VEVENT", f"UID:{e['id']}@book-promo-studio", f"DTSTAMP:{stamp}",
                  f"DTSTART:{start:%Y%m%dT%H%M%S}", "DURATION:PT15M",
                  "SUMMARY:" + _esc(f"Post on {e['platform']}: {e['title']}"),
                  "DESCRIPTION:" + _esc(f"{book_title}\n{e.get('note', '')}".strip()),
                  "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Time to post", "TRIGGER:-PT15M", "END:VALARM",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

from datetime import date, datetime

import pytest

from promo import render, results, schedule


def test_kpis(book, make_render):
    for n, views in enumerate([100, 300, 50, 60], 1):
        make_render(book["id"], n, views=views, likes=views // 10)
    k = results.kpis(results.rows(book["id"]))
    assert k["made"] == 4 and k["logged"] == 4 and k["views"] == 510 and k["best"]["views"] == 300


def test_rows_skip_drafts_and_flag_unlogged(book, make_render):
    make_render(book["id"], 1, views=10)
    make_render(book["id"], 2, draft=True, views=999)
    make_render(book["id"], 3)
    rows = results.rows(book["id"])
    assert len(rows) == 2 and sorted(r["logged"] for r in rows) == [False, True]


def test_insights_need_two_videos_per_group():
    def mk(hook, views):
        return {"logged": True, "views": views, "Hook type": hook, "hook_score": None, "engagement": 0}
    assert results.insights([mk("POV", 1000), mk("question", 100)]) == []
    out = results.insights([mk("POV", 1000), mk("POV", 900), mk("question", 100), mk("question", 120)])
    assert out and "POV" in out[0]


def test_entry_validates():
    with pytest.raises(ValueError):
        schedule.entry("r", "t", date(2026, 1, 1), "25:00", "TikTok")
    with pytest.raises(ValueError):
        schedule.entry("r", "t", date(2026, 1, 1), "19:00", "MySpace")


def test_plan_spreads_posts_and_never_double_books(book, make_render):
    for n in range(1, 5):
        make_render(book["id"], n, views=n * 10)
    renders = render.list_renders(book["id"])
    now = datetime(2026, 3, 2, 8, 0)  # a Monday
    first = schedule.plan(book["id"], renders, per_week=2, weeks=1, now=now)
    assert len(first) == 2 and all(e["status"] == "planned" for e in first)
    again = schedule.plan(book["id"], renders, per_week=2, weeks=1, now=now)
    assert {e["render"] for e in first}.isdisjoint({e["render"] for e in again})


def test_due_only_lists_planned_posts_in_the_past():
    past = schedule.entry("r", "t", date(2026, 1, 1), "09:00", "TikTok")
    done = {**past, "status": "posted"}
    future = schedule.entry("r2", "t", date(2030, 1, 1), "09:00", "TikTok")
    assert schedule.due([past, done, future], datetime(2026, 6, 1)) == [past]


def test_ics_export():
    e = schedule.entry("r", "a, b; c", date(2026, 1, 1), "09:00", "TikTok")
    assert "BEGIN:VCALENDAR" in schedule.to_ics([e], "Book")

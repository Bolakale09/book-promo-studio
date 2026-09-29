"""Studio dashboard and the set-up steps: book, characters, pages, viral format."""
from pathlib import Path

import pandas as pd
import streamlit as st

from promo import analyze, book as bk, config, ingest, jobs, render, script, visuals, voice
from promo.genres import GENRES

from . import theme as t
from .common import (PAGES, go, image_price, money, need_book, next_step, book_progress, run_safely, save_upload,
                     start_task, task_panel,
                     sentences, video_src)


# ---- Studio (dashboard) ----------------------------------------------------------------------

def home() -> None:
    b = need_book()
    g = GENRES[b["genre"]]
    steps = book_progress(b)
    required = [s for s in steps if not s.get("optional")]
    done = sum(s["done"] for s in required)
    nxt = next((s for s in steps if not s["done"] and not s.get("optional")), None)

    uri = t.img_uri(bk.path(b, "cover"), 200)
    cover = f'<img src="{uri}">' if uri else f'<div class="bps-cover-ph">{t.GENRE_ICON[b["genre"]]}</div>'
    ms = bk.path(b, "manuscript")
    meta = " · ".join(x for x in [b.get("author"), f"{bk.page_count(b)} pages" if ms and ms.exists() else "",
                                  f"sells on {b.get('where_to_buy') or 'Amazon'}"] if x)
    t.md(f'<div class="bps-hero">{cover}<div style="flex:1"><div class="bps-eyebrow">Your book</div>'
         f'<h2>{t.esc(b["title"])}</h2><div class="meta">{t.esc(meta)}</div>'
         f'{t.chip(t.GENRE_ICON[b["genre"]] + " " + g["label"], "gold")}{t.chip("~" + str(g["target_seconds"]) + "s videos")}'
         f'{t.chip("🎙 " + voice.default_voice(b["genre"]) + " voice")}'
         f'<div style="margin-top:.9rem;max-width:420px"><div class="bps-muted">Set-up {done}/{len(required)} steps</div>'
         f'{t.bar(done / len(required))}</div></div></div>')

    scripts = script.load_scripts(b["id"])
    renders = render.list_renders(b["id"])
    best = max((r.get("views") or 0 for r in renders), default=0)
    from promo import budget
    t.stats([("Scripts", str(len(scripts)), "ready to render"), ("Videos", str(len(renders)), "rendered"),
             ("Best views", f"{best:,}", "log views in Videos"),
             ("Spent this month", money(budget.spent_this_month()), f"of {money(config.MONTHLY_BUDGET_USD)}")])
    from promo import schedule
    due = schedule.due(schedule.load(b["id"]))
    if due:
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.info(f"📣 {len(due)} post(s) are due: {due[0]['title']} on {due[0]['platform']}"
                + (f" and {len(due) - 1} more" if len(due) > 1 else ""))
        if c2.button("Open calendar", width="stretch"):
            go("calendar")
    st.write("")
    quick_video_card(b)

    left, right = st.columns([5, 4], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("#### Your workflow")
            rows = []
            for i, s in enumerate(steps, 1):
                cls = "done" if s["done"] else ("next" if s is nxt else "")
                mark = "✓" if s["done"] else str(i)
                opt = '<span class="opt">optional</span>' if s.get("optional") else ""
                rows.append(f'<div class="bps-check {cls}"><div class="dot">{mark}</div>'
                            f'<div class="lbl">{t.esc(s["label"])}</div>{opt}</div>')
            t.md("".join(rows))
            st.write("")
            if nxt:
                if st.button(f"Next: {nxt['label']} →", type="primary", width="stretch"):
                    go(nxt["page"])
            else:
                c1, c2 = st.columns(2)
                if c1.button("✍️ Write more scripts", type="primary", width="stretch"):
                    go("scripts")
                if c2.button("🎬 Render a video", width="stretch"):
                    go("render")

    with right:
        with st.container(border=True):
            st.markdown("#### Latest videos")
            active = jobs.active(b["id"], jobs.HEAVY)
            if renders:
                cols = st.columns(2)
                for col, r in zip(cols, renders[:2]):
                    src = video_src(r["path"])
                    if src:
                        col.video(src)
                    col.caption(f"**{r['variant'].get('name')}** · {r['seconds']}s")
                st.page_link(PAGES["videos"], label="See all videos →")
            elif not active:
                t.empty("🎬", "No videos yet - write a script, then render it.")

        d = b.get("digest") or {}
        if d.get("quotes"):
            with st.container(border=True):
                st.markdown("#### A line that could stop the scroll")
                q = d["quotes"][0]
                t.md(f'<div class="bps-quote">“{t.esc(q.get("text"))}”</div>'
                     f'<div class="bps-muted">page {q.get("page")} · {t.esc(q.get("why", ""))}</div>')


QUICK_MIXES = {"💸 Free only": (True, 0), "⚖️ Balanced": (False, 1)}


def quick_video_card(b: dict) -> None:
    """One click: read the book (if needed) -> write 3 scripts -> render the strongest."""
    ms = bk.path(b, "manuscript")
    if not (b.get("blurb") or (ms and ms.exists())):
        return
    with st.container(border=True):
        c1, c2 = st.columns([3, 2], vertical_alignment="center")
        with c1:
            st.markdown("#### ⚡ Quick video")
            st.caption(("Reads your manuscript, " if not b.get("digest") and ms else "") + "writes 3 scripts and "
                       "renders the strongest one - all in the background. Fine-tune later in Scripts.")
            mix = st.segmented_control("Visual mix", list(QUICK_MIXES), default="⚖️ Balanced", key="quick_mix",
                                       label_visibility="collapsed") or "⚖️ Balanced"
            draft = st.toggle("Draft quality (720p, about twice as fast)", False, key="quick_draft")
        free_only, max_ai_video = QUICK_MIXES[mix]
        low, high = (0.02, 0.06) if free_only else (0.05, 0.6)
        running = jobs.active(b["id"], {"quick"})
        with c2:
            t.md(f'<div class="bps-muted">Expected cost</div><div style="font:700 1.6rem Fraunces,serif">'
                 f'{money(low)} - {money(high)}</div><div class="bps-muted">depends on the AI shots it picks</div>')
            if st.button("⚡ Make a video now", type="primary", width="stretch", disabled=bool(running)):
                from promo import config as cfg
                start_task("quick", b["id"], "Quick video", {
                    "args": {"n": 3, "max_ai_video": max_ai_video, "free_only": free_only,
                             "has_broll": bool(render._broll_clips(b)), "has_stock": bool(cfg.PEXELS_API_KEY)},
                    "options": {"quality_check": True, "draft": draft}},
                    note="Quick video started - it will appear in Videos in a few minutes")
        task_panel(b["id"], {"quick"})


# ---- 1 · Book -------------------------------------------------------------------------------

def book_page() -> None:
    b = need_book()
    t.header("Step 1 · Book", "Your book", "The genre decides the angle, hooks, narrator voice, pacing and look of "
                                             "every video. The manuscript gives the real pages the videos show.")
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("#### Details")
            with st.form("book_details", border=False):
                b["title"] = st.text_input("Title", b["title"])
                c1, c2 = st.columns(2)
                b["author"] = c1.text_input("Author / pen name", b.get("author", ""))
                b["audience"] = c2.text_input("Who is it for?", b.get("audience", ""),
                                              placeholder="e.g. new nurse practitioners")
                b["genre"] = st.pills("Genre", list(GENRES), default=b["genre"],
                                      format_func=lambda k: f"{t.GENRE_ICON[k]} {GENRES[k]['label']}") or b["genre"]
                b["blurb"] = st.text_area("Blurb / what the book is about", b.get("blurb", ""), height=110)
                c1, c2 = st.columns(2)
                b["where_to_buy"] = c1.text_input("Where to buy", b.get("where_to_buy", "Amazon"))
                b["link"] = c2.text_input("Link (for your caption)", b.get("link", ""))
                if st.form_submit_button("Save details", type="primary"):
                    bk.save(b)
                    st.toast("Saved", icon="✅")
                    st.rerun()

        g = GENRES[b["genre"]]
        with st.expander(f"{t.GENRE_ICON[b['genre']]} The {g['label']} playbook the AI follows"):
            c1, c2 = st.columns(2)
            c1.markdown("**Angles**\n" + "\n".join(f"- {a}" for a in g["angles"]))
            c2.markdown("**Hook style**\n" + "\n".join(f"- _{h}_" for h in g["hook_examples"]))
            t.chips([("Tone: " + g["tone"], ""), (f"~{g['target_seconds']}s", ""),
                     ("Voice: " + voice.default_voice(b["genre"]), "gold"),
                     ("Ends: " + g["breadcrumb"].format(title=b["title"]), "")])
            st.caption("Rules: " + g["rules"])

    with right:
        with st.container(border=True):
            st.markdown("#### Cover")
            c1, c2 = st.columns([1, 2])
            thumb = bk.cover_thumb(b, 220)
            if thumb:
                c1.image(thumb)
            else:
                c1.markdown(f'<div class="bps-cover-ph">{t.GENRE_ICON[b["genre"]]}</div>', unsafe_allow_html=True)
            up = c2.file_uploader("Front cover", ["png", "jpg", "jpeg", "webp"], key=f"cover_{b['id']}")
            if up and c2.button("Use this cover", type="primary"):
                b["cover"] = save_upload(up, bk.book_dir(b["id"]), "cover")
                bk.save(b)
                st.rerun()

        with st.container(border=True):
            st.markdown("#### Manuscript")
            ms = bk.path(b, "manuscript")
            if ms and ms.exists():
                t.chips([(f"📄 {ms.suffix[1:].upper()}", "green"), (f"{bk.page_count(b)} pages", "green")])
            up = st.file_uploader("PDF, DOCX or TXT", ["pdf", "docx", "txt", "md"], key=f"ms_{b['id']}")
            if up and st.button("Use this manuscript", type="primary"):
                b["manuscript"] = save_upload(up, bk.book_dir(b["id"]), "manuscript")
                (bk.book_dir(b["id"]) / "pages.json").unlink(missing_ok=True)
                b["digest"] = None
                bk.save(b)
                st.rerun()

        with st.container(border=True):
            st.markdown("#### Desk & your own clips")
            c1, c2 = st.columns([1, 2])
            bg = bk.path(b, "background")
            if bg and bg.exists():
                c1.image(str(bg))
                if b.get("background_v", 0) < visuals.OVERHEAD_DESK and b.get("background", "").startswith("img_"):
                    st.info("💡 This desk photo was made with the old angled style, so your book and pages can look "
                            "pasted on. Click **New AI desk photo**: new ones are shot from directly above, so "
                            "everything lies naturally on the table.")
            else:
                c1.caption("Plain wood until you add a desk photo (made automatically on first render).")
            if c2.button(f"✨ {'New ' if bg and bg.exists() else ''}AI desk photo ({money(image_price())})",
                         width="stretch", disabled=bool(jobs.active(b["id"], {"desk"}))):
                start_task("desk", b["id"], "Desk photo")
            up = c2.file_uploader("…or upload your own photo, taken from directly above", ["png", "jpg", "jpeg"],
                                  key=f"bg_{b['id']}")
            if up and c2.button("Use photo"):
                b["background"] = save_upload(up, bk.book_dir(b["id"]), "background")
                bk.save(b)
                st.rerun()
            clips = render._broll_clips(b)
            ups = st.file_uploader(f"B-roll clips ({len(clips)} saved): you reading, the printed book, your desk",
                                   ["mp4", "mov", "m4v", "webm"], accept_multiple_files=True, key=f"broll_{b['id']}")
            if ups and st.button("Save clips"):
                d = bk.book_dir(b["id"]) / "broll"
                d.mkdir(exist_ok=True)
                for u in ups:
                    (d / Path(u.name).name).write_bytes(u.getbuffer())
                st.rerun()

    # AI read-through
    st.write("")
    with st.container(border=True):
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.markdown("#### 🧠 AI read-through")
        c1.caption("Finds the emotional promise, target readers, characters and the most scroll-stopping lines with "
                   "page numbers. About $0.01-0.03, once per book.")
        ms = bk.path(b, "manuscript")
        label = "Read it again" if b.get("digest") else "Read my manuscript"
        if c2.button(label, type="secondary" if b.get("digest") else "primary", width="stretch",
                     disabled=not (ms and ms.exists())):
            start_task("digest", b["id"], "AI read-through")
        d = b.get("digest")
        if d:
            c1, c2 = st.columns(2)
            with c1:
                t.md(f'<div class="bps-muted">Summary</div><p>{t.esc(d.get("summary", ""))}</p>'
                     f'<div class="bps-muted">Emotional promise</div><p>{t.esc(d.get("emotional_promise", ""))}</p>')
            with c2:
                t.md('<div class="bps-muted">Readers who&#39;ll love it</div>'
                     + "".join(t.chip(x, "gold") for x in d.get("target_readers", [])[:8])
                     + '<div class="bps-muted" style="margin-top:.6rem">Hooks &amp; tropes</div>'
                     + "".join(t.chip(x) for x in d.get("tropes_or_hooks", [])[:8]))
            quotes = d.get("quotes", [])
            if quotes:
                st.markdown("**Best lines** - tick the ones to show in videos")
                df = pd.DataFrame([{"feature": False, "page": q.get("page"), "line": q.get("text"),
                                    "why": q.get("why", "")} for q in quotes])
                ed = st.data_editor(df, hide_index=True, width="stretch", disabled=["page", "line", "why"],
                                    column_config={"feature": st.column_config.CheckboxColumn("⭐", width="small"),
                                                   "line": st.column_config.TextColumn(width="large")},
                                    key=f"quotes_{b['id']}")
                picked = ed[ed["feature"]]
                if st.button(f"⭐ Feature {len(picked)} line(s)", disabled=picked.empty):
                    have = {(f["page"], f["text"]) for f in b.get("featured") or []}
                    for _, r in picked.iterrows():
                        if (int(r["page"] or 1), r["line"]) not in have:
                            b.setdefault("featured", []).append({"page": int(r["page"] or 1), "text": r["line"]})
                    bk.save(b)
                    st.toast("Added to featured pages", icon="⭐")

    task_panel(b["id"], {"digest", "desk"})
    with st.expander("⚠️ Delete this book"):
        st.caption("Deletes the book with its manuscript, characters, scripts and videos - here and in cloud storage. "
                   "Make a backup first (💾 Backup & storage) if you might want it back.")
        confirm = st.text_input(f"Type the title to confirm: {b['title']}", key=f"del_book_{b['id']}")
        if st.button("Delete book permanently", disabled=confirm.strip() != b["title"].strip()):
            run_safely(bk.delete_book, b["id"])
            st.session_state.pop("book_id", None)
            st.toast("Book deleted", icon="🗑")
            st.rerun()
    next_step("characters", "add the characters your videos should show")


# ---- 2 · Characters -------------------------------------------------------------------------

def characters_page() -> None:
    b = need_book()
    t.header("Step 2 · Characters", "Who appears in the videos",
             "Add a photo to keep the same face in every AI shot, or let the AI create a portrait once. Only use "
             "photos of real people you have permission to use.")
    chars = b.setdefault("characters", [])
    c1, c2 = st.columns([1, 1])
    with c1.popover("➕ Add a character", width="stretch"):
        with st.form("add_char", clear_on_submit=True, border=False):
            name = st.text_input("Name")
            desc = st.text_area("Look + personality", height=110,
                                placeholder="e.g. 30s, Nigerian, short natural hair, gold hoop earrings, tired kind "
                                            "eyes, nurse's scrubs; quiet but fierce")
            photo = st.file_uploader("Reference photo (optional)", ["png", "jpg", "jpeg", "webp"])
            if st.form_submit_button("Add character", type="primary", width="stretch") and name.strip():
                c = {"name": name.strip(), "description": desc.strip()}
                if photo:
                    c["ref_image"] = "characters/" + save_upload(photo, bk.book_dir(b["id"]) / "characters",
                                                                 bk.slug(name))
                chars.append(c)
                bk.save(b)
                st.rerun()
    found = [c for c in (b.get("digest") or {}).get("characters", [])
             if c.get("name", "").lower() not in {x["name"].lower() for x in chars}]
    if found and c2.button(f"✨ Import {len(found)} character(s) found in the manuscript", width="stretch"):
        chars.extend({"name": c["name"], "description": c.get("description", "")} for c in found)
        bk.save(b)
        st.rerun()

    if not chars:
        t.empty("🎭", "No characters yet. Characters are optional - pages, cover and stock footage work without them.")
    for row in range(0, len(chars), 4):
        cols = st.columns(4)
        for col, (i, c) in zip(cols, list(enumerate(chars))[row:row + 4]):
            with col, st.container(border=True):
                ref = bk.book_dir(b["id"]) / c["ref_image"] if c.get("ref_image") else None
                uri = t.img_uri(ref, 360)
                t.md(f'<img src="{uri}" style="width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:12px">'
                     if uri else f'<div class="bps-avatar">{t.esc(c["name"][:1].upper())}</div>')
                t.md(f'<div class="bps-card-title" style="margin-top:.6rem">{t.esc(c["name"])}</div>'
                     f'<div class="bps-muted">{t.esc((c.get("description") or "")[:140])}</div>')
                st.write("")
                a, d = st.columns([3, 1])
                if a.button("✨ AI portrait" if not uri else "↻ New portrait", key=f"port_{i}", width="stretch",
                            help=f"About {money(image_price())}"):
                    start_task("portrait", b["id"], c["name"], {"name": c["name"]})
                if d.button("🗑", key=f"delc_{i}", width="stretch", help="Remove"):
                    chars.pop(i)
                    bk.save(b)
                    st.rerun()
    task_panel(b["id"], {"portrait"})
    next_step("pages", "pick the pages and lines your videos turn to")


# ---- 3 · Pages ------------------------------------------------------------------------------

@st.cache_data(show_spinner=False, max_entries=48)
def _page_preview(book_id: str, ms_mtime: float, page: int, line: str, width: int):
    img = bk.preview_page(bk.load(book_id), page, line)
    img.thumbnail((width, width * 2))
    return img


def pages_page() -> None:
    b = need_book()
    t.header("Step 3 · Pages", "Pages to show, page to page",
             "In the video the previous pages turn, then your line is swept with a highlighter while the camera "
             "pushes in. Featured lines are used first when the AI writes scripts.")
    ms = bk.path(b, "manuscript")
    if not (ms and ms.exists()):
        t.empty("📄", "Upload the manuscript in Step 1 first.")
        if st.button("Go to Book"):
            go("book")
        return
    n = max(1, bk.page_count(b))
    all_pages = {p["page"]: p["text"] for p in bk.pages(b)}
    mt = ms.stat().st_mtime

    left, right = st.columns([3, 2], gap="large")
    with left, st.container(border=True):
        if st.session_state.get("pick_page", 1) > n:
            st.session_state["pick_page"] = 1
        def step_page(d: int) -> None:
            st.session_state["pick_page"] = min(n, max(1, st.session_state.get("pick_page", 1) + d))

        c1, c2, c3 = st.columns([1, 3, 1], vertical_alignment="bottom")
        c1.button("◀", width="stretch", on_click=step_page, args=(-1,),
                  disabled=st.session_state.get("pick_page", 1) <= 1)
        page = c2.slider("Page", 1, n, key="pick_page") if n > 1 else 1
        c3.button("▶", width="stretch", on_click=step_page, args=(1,), disabled=page >= n)
        opts = sentences(all_pages.get(page, ""))
        pick = st.selectbox("Line to highlight", ["(type my own)"] + opts, key=f"line_{page}")
        line = st.text_area("Highlight text (exactly as on the page)", "" if pick == "(type my own)" else pick,
                            key=f"hl_{page}_{pick}", height=90)
        if st.button("⭐ Feature this page + line", type="primary", width="stretch"):
            b.setdefault("featured", []).append({"page": int(page), "text": line.strip()})
            bk.save(b)
            st.toast(f"Page {page} featured", icon="⭐")
            st.rerun()
    with right:
        img = run_safely(_page_preview, b["id"], mt, int(page), line.strip(), 520)
        if img is not None:
            st.image(img, caption=f"Page {page} of {n} - preview with highlight")

    feats = b.get("featured") or []
    st.markdown(f"#### Featured ({len(feats)})")
    if not feats:
        t.empty("⭐", "Nothing featured yet - or tick lines in the AI read-through on the Book step.")
    for row in range(0, len(feats), 4):
        cols = st.columns(4)
        for col, (i, f) in zip(cols, list(enumerate(feats))[row:row + 4]):
            with col, st.container(border=True):
                img = run_safely(_page_preview, b["id"], mt, int(f["page"]), f["text"], 300)
                if img is not None:
                    st.image(img)
                t.md(f'{t.chip("p." + str(f["page"]), "gold")}<div class="bps-muted">'
                     f'{t.esc((f["text"] or "(whole page)")[:110])}</div>')
                if st.button("Remove", key=f"delf_{i}", width="stretch"):
                    feats.pop(i)
                    bk.save(b)
                    st.rerun()
    next_step("scripts", "write scripts that use these pages")


# ---- 4 · Viral format ------------------------------------------------------------------------

def formats_page() -> None:
    need_book()
    t.header("Step 4 · Viral format (optional)", "Copy what already works",
             "Paste a TikTok / Reels / Shorts link of a book video that went viral. The app studies its structure - "
             "hook, pacing, overlays, ending - never its words. About $0.01 per video.")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        url = c1.text_input("Video link", placeholder="https://www.tiktok.com/@.../video/...")
        up = c2.file_uploader("…or upload the video", ["mp4", "mov", "webm"])
        if st.button("🔍 Analyze format", type="primary", disabled=not (url or up)):
            with st.status("Analyzing the reference video...", expanded=True) as stt:
                try:
                    if up:
                        tmp = config.REFS_DIR / Path(up.name).name
                        tmp.write_bytes(up.getbuffer())
                        video = ingest.import_local(tmp, up.name)
                        tmp.unlink(missing_ok=True)
                    else:
                        stt.write("Downloading...")
                        video = ingest.download(url.strip())
                    bp = analyze.analyze_reference(video, progress=stt.write)
                    stt.update(label=f"Format ready: {bp.get('summary', '')}", state="complete")
                except Exception as e:
                    stt.update(label=f"Failed: {e}", state="error")

    bps = analyze.list_blueprints()
    st.markdown(f"#### Saved formats ({len(bps)})")
    if not bps:
        t.empty("🔁", "No formats yet - the built-in genre format works great on its own.")
    for bp_id, bp in bps.items():
        sc = bp.get("score", {})
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f'<div class="bps-card-title">{t.esc(bp.get("summary", bp_id))}</div>', unsafe_allow_html=True)
            with c1:
                t.chips([(f"Hook {sc.get('hook', '?')}/10", "gold"), (f"Emotion {sc.get('emotion', '?')}/10", ""),
                         (f"{bp.get('total_seconds', '?')}s", ""), (bp.get("hook", {}).get("type", ""), "blue")]
                        + [(g, "") for g in bp.get("best_for_genres", [])[:4]])
            c1.caption(bp.get("why_it_works", ""))
            if c2.button("Use for scripts", key=f"use_{bp_id}", type="primary", width="stretch"):
                go("scripts", bp_choice=bp_id)
            if c2.button("Delete", key=f"delbp_{bp_id}", width="stretch"):
                (config.BLUEPRINTS_DIR / f"{bp_id}.json").unlink(missing_ok=True)
                st.rerun()
            with st.expander("Structure"):
                st.dataframe(pd.DataFrame(bp.get("structure", [])), hide_index=True, width="stretch")
    next_step("scripts", "write scripts")

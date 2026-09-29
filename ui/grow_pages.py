"""Getting the videos out and learning from them: brand kit, own voice, music, hook lab, posting kit, calendar, results."""
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw

from promo import book as bk, brand, config, hooks, jobs, kit, music as musiclib, myvoice, render, results, schedule, \
    script, storage
from promo.genres import GENRES

from . import theme as t
from .common import MUSIC_EXT, go, need_book, next_step, run_safely, start_task, task_panel, video_src

PLATFORM_ICON = {"TikTok": "🎵", "Instagram Reels": "📸", "YouTube Shorts": "▶️"}
AUDIO_TYPES = ["wav", "mp3", "m4a", "aac", "ogg", "webm", "flac"]


# ---- brand kit ------------------------------------------------------------------------------

def _preview(draft: dict, book: dict | None, last: bool) -> Image.Image:
    w, h = 300, 533
    if book:
        try:
            img = bk.background(book).convert("RGB").resize((w, h))
        except Exception:
            img = Image.new("RGB", (w, h), (46, 34, 26))
    else:
        img = Image.new("RGB", (w, h), (46, 34, 26))
    d = ImageDraw.Draw(img)
    k = w / 1080
    accent = brand.accent_rgb((240, 180, 41), draft)
    font_name = brand.caption_font("Arial Black", draft)
    fnt = bk.font(font_name, 30)
    if last and draft["cta"] and draft["cta_on_end"]:
        d.rounded_rectangle((26, 92, w - 26, 150), radius=8, fill=(255, 255, 255))
        d.text((w / 2, 121), draft["cta"][:34], font=bk.font("Arial Black", 17), fill=(20, 20, 20), anchor="mm")
    else:
        x = 36
        y = int(h * 0.64)
        for i, word in enumerate(("Read", "this", "tonight")):
            txt = word.upper() if font_name == "Arial Black" else word
            d.text((x, y), txt, font=fnt, fill=accent if i == 1 else (255, 255, 255), stroke_width=3,
                   stroke_fill=(0, 0, 0))
            x += int(d.textlength(txt + " ", font=fnt))
    mark = brand.watermark((w, h), k * 1.7, draft)
    if mark:
        img.paste(mark[0], mark[1], mark[0])
    return img


def brand_page() -> None:
    b = need_book()
    t.header("Set up · Brand kit", "Make every video look like yours",
             "Set it once: your handle and logo appear on every video, captions use your colour and font, and your "
             "hashtags and call-to-action join every post.")
    kit0 = brand.load()
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("#### Who you are")
            c1, c2 = st.columns(2)
            name = c1.text_input("Author / brand name", kit0["name"], placeholder="e.g. Jane Author")
            handle = c2.text_input("Handle", kit0["handle"], placeholder="@janeauthor",
                                   help="Shown as a small watermark on every video.")
            tagline = st.text_input("Tagline (optional)", kit0["tagline"], placeholder="Stories for late-night readers")
            up = st.file_uploader("Logo (PNG with a transparent background looks best)",
                                  ["png", "jpg", "jpeg", "webp"], key="brand_logo_up")
            if up and st.session_state.get("_logo_done") != up.file_id:
                run_safely(brand.save_logo, up.getvalue(), up.name)
                brand.save({**brand.load(), "logo": "logo.png"})
                st.session_state["_logo_done"] = up.file_id
                st.rerun()
            if brand.logo_path(kit0) and st.button("Remove logo"):
                brand.remove_logo()
                st.session_state.pop("_logo_done", None)
                st.rerun()

        with st.container(border=True):
            st.markdown("#### Look")
            c1, c2 = st.columns(2)
            own_colour = c1.checkbox("Use my own caption colour", bool(kit0["accent"]),
                                     help="Otherwise captions use the genre's colour.")
            colour = c1.color_picker("Caption highlight colour", kit0["accent"] or "#F0B429", disabled=not own_colour)
            font = c2.selectbox("Caption font", brand.FONTS, brand.FONTS.index(kit0["font"]) if kit0["font"] in
                                brand.FONTS else 0, format_func=lambda f: brand.FONT_LABEL[f])
            c1, c2 = st.columns(2)
            watermark = c1.toggle("Watermark (logo + handle)", kit0["watermark"])
            position = c2.selectbox("Watermark position", brand.POSITIONS, brand.POSITIONS.index(kit0["position"])
                                    if kit0["position"] in brand.POSITIONS else 0, disabled=not watermark)

        with st.container(border=True):
            st.markdown("#### Every post")
            cta = st.text_input("Call-to-action", kit0["cta"], placeholder="Link in bio - get it on Amazon")
            cta_on_end = st.checkbox("Show it as the text on the last scene", kit0["cta_on_end"],
                                     help="Replaces the last scene's overlay text in new videos.")
            tags = st.text_input("Your standing hashtags", " ".join(kit0["hashtags"]),
                                 placeholder="#booktok #indieauthor")
        draft = {**kit0, "name": name, "handle": handle.strip(), "tagline": tagline, "accent": colour if own_colour
                 else "", "font": font, "watermark": watermark, "position": position, "cta": cta,
                 "cta_on_end": cta_on_end, "hashtags": brand.hashtag_list(tags)}
        if draft["handle"] and not draft["handle"].startswith("@"):
            draft["handle"] = "@" + draft["handle"]
        if st.button("💾 Save brand kit", type="primary"):
            try:
                brand.save(draft)
                st.toast("Brand kit saved - it applies to videos you render from now on", icon="🎨")
            except ValueError as e:
                st.error(str(e))
            st.rerun()
    with right:
        st.markdown("**Preview**")
        c1, c2 = st.columns(2)
        c1.image(_preview(draft, b, False), caption="During the video", width="stretch")
        c2.image(_preview(draft, b, True), caption="Last scene", width="stretch")
        st.caption("Applies to new videos. Turn it off per video on the Render page.")
    next_step("scripts", "write scripts - every video you render will use this look")


# ---- own voice -------------------------------------------------------------------------------

@st.dialog("Record your narration", width="large")
def record_dialog(b: dict, v: dict) -> None:
    lines = myvoice.script_lines(v)
    st.caption("Read the whole script in one go at a natural pace - pauses between lines are fine, the app finds "
               "where each line starts. Quiet room, phone or laptop mic is enough.")
    for n, beat, text in lines:
        t.md(f'<div class="bps-quote"><span class="bps-muted">Scene {n} · {t.esc(beat)}</span><br>'
             f'<span style="font-size:1.15rem">{t.esc(text)}</span></div>')
    tab_rec, tab_up = st.tabs(["🎙 Record now", "⬆ Upload a recording"])
    data, fname = None, ""
    with tab_rec:
        rec = st.audio_input("Press the microphone, read the script, press stop", key=f"rec_{v.get('id')}")
        if rec:
            data, fname = rec.getvalue(), "recording.wav"
    with tab_up:
        up = st.file_uploader("A recording of the script (any common audio format)", AUDIO_TYPES,
                              key=f"recup_{v.get('id')}")
        if up:
            data, fname = up.getvalue(), up.name
    clean = st.checkbox("Clean up the sound (remove hum and hiss, even out the volume, trim silence)", True)
    if st.button("Save my recording", type="primary", disabled=data is None):
        with st.spinner("Cleaning up the sound..."):
            info = run_safely(myvoice.save, b["id"], v["id"], data, fname, v, clean)
        if info:
            with st.spinner("Listening to check it against the script..."):
                run_safely(myvoice.analyse, myvoice.wav_path(b["id"], v["id"]), myvoice.narration_text(v))
            st.toast("Recording saved", icon="🎙")
            st.rerun()


def _match(book_id: str, v: dict) -> float | None:
    """How well the recording matches the script, if it has been listened to already (never transcribes here)."""
    wav = myvoice.wav_path(book_id, v["id"])
    cache = wav.with_name(f"{wav.stem}.words-{myvoice.text_hash(myvoice.narration_text(v))}.json")
    try:
        return json.loads(cache.read_text(encoding="utf-8")).get("match")
    except (OSError, ValueError):
        return None


def own_voice_block(b: dict, v: dict) -> tuple[Path | None, str]:
    """The 'My own voice' controls. Returns (recording, problem) - problem is non-empty when it can't be used yet."""
    if not myvoice.narration_text(v):
        return None, "This script has no narration to read - it is text-only."
    info = myvoice.info(b["id"], v["id"], v)
    if not info:
        st.caption("Read the script into your microphone (or upload a recording). Your voice replaces the AI "
                   "narrator; captions and scene timing follow it. Costs nothing extra.")
        if st.button("🎙 Record or upload my voice", type="primary", width="stretch"):
            record_dialog(b, v)
        return None, "Record or upload your narration first."
    st.audio(info["path"])
    m = _match(b["id"], v)
    t.chips([(f"{info['seconds']:.0f}s", ""), ("cleaned" if info.get("cleaned") else "raw", ""),
             (f"{round(m * 100)}% match", "green" if m >= 0.8 else "gold" if m >= 0.6 else "red") if m is not None
             else ("not checked yet", "")])
    problem = ""
    if info.get("script_changed"):
        st.warning("The script changed after you recorded. Record it again so the captions line up.")
        problem = "Re-record: the script changed."
    elif m is not None and m < 0.6:
        st.warning("Your recording doesn't match the script well (words missing or different). Captions may be off - "
                   "re-record, or edit the script to what you actually said.")
    c1, c2 = st.columns(2)
    if c1.button("🎙 Re-record", width="stretch"):
        record_dialog(b, v)
    if c2.button("🗑 Remove", width="stretch"):
        myvoice.remove(b["id"], v["id"])
        st.rerun()
    return Path(info["path"]), problem


# ---- music ------------------------------------------------------------------------------------

def music_picker(genre: str) -> tuple[str | None, bool]:
    """Returns (music option for render, chosen?)."""
    sug = musiclib.suggested(genre)
    tracks = sorted(p for p in config.MUSIC_DIR.glob("*") if p.suffix.lower() in MUSIC_EXT)
    order = [sug] + [k for k in musiclib.STYLES if k != sug]
    choices = [None] + [f"builtin:{k}" for k in order] + [str(p) for p in tracks]

    def label(c):
        if c is None:
            return "No music"
        if c.startswith("builtin:"):
            k = c.split(":", 1)[1]
            s = musiclib.STYLES[k]
            return f"🎵 {s['label']} - {s['mood']}" + ("  ★ suits this genre" if k == sug else "")
        return f"📁 {Path(c).name}"

    pick = st.selectbox("Music", choices, 1, format_func=label, key="music_pick")
    if pick and pick.startswith("builtin:"):
        with st.spinner("Preparing a preview (first time only)..."):
            pv = run_safely(musiclib.preview, pick.split(":", 1)[1])
        if pv:
            st.audio(str(pv))
        st.caption("Built-in music is generated by the app - royalty-free, nothing to license or download.")
    return pick, pick is not None


# ---- hook lab ---------------------------------------------------------------------------------

def hook_chip(v: dict) -> tuple[str, str] | None:
    ht = v.get("hook_test")
    if not ht or ht.get("score") is None:
        return None
    s = ht["score"]
    return (f"Hook {s:.1f}/10" + (" · improved" if ht.get("swapped") else ""),
            "green" if s >= 7 else "gold" if s >= 5 else "red")


def hook_lab(b: dict, scripts: list[dict]) -> None:
    rows = hooks.load_lab(b["id"])
    with st.expander(f"🧪 Hook lab ({len(rows)} tested)"):
        st.caption("The first two seconds decide everything. A panel of imagined viewers (built from your book's "
                   "readers) scores hooks before you spend money rendering them. It's an AI's opinion - real views "
                   "on the Results page have the final say.")
        busy = bool(jobs.active(b["id"], {"hooks"}))
        c1, c2 = st.columns([1, 3], vertical_alignment="bottom")
        n = c1.number_input("New ideas", 0, 15, 8, key="hook_n")
        mine = c2.text_input("…or test your own hook", key="hook_mine", placeholder="e.g. She never planned to fall for him")
        if st.button("🧪 Test hooks (about 3¢)", type="primary", disabled=busy or not (n or mine.strip())):
            start_task("hooks", b["id"], "Hook test", {"n": int(n), "custom": [mine] if mine.strip() else []})
        if not rows:
            return
        target = st.selectbox("Use a hook in script", range(len(scripts)), format_func=lambda i: scripts[i].get(
            "name", f"Script {i + 1}"), key="hook_target") if scripts else None
        for i, r in enumerate(rows[:12]):
            with st.container(border=True):
                c1, c2 = st.columns([5, 1], vertical_alignment="center")
                with c1:
                    tone = "green" if (r.get("score") or 0) >= 7 else "gold" if (r.get("score") or 0) >= 5 else "red"
                    t.chips([(f"{r['score']:.1f}/10" if r.get("score") is not None else "-", tone),
                             (r.get("hook_type") or "", "gold"), ("yours" if r.get("source") == "yours" else "AI idea", "")]
                            + ([("cringe risk", "red")] if r.get("cringe") else []))
                    t.md(f'<div class="bps-quote">{t.esc(r.get("overlay"))}</div>')
                    if r.get("voiceover") and r["voiceover"] != r.get("overlay"):
                        st.caption(f"Said: {r['voiceover']}")
                    sub = r.get("sub") or {}
                    if sub:
                        st.caption(" · ".join(f"{hooks.LABELS[k]} {sub[k]:.0f}" for k in hooks.WEIGHTS if k in sub)
                                   + (f" — {r['note']}" if r.get("note") else ""))
                if c2.button("Use", key=f"usehook_{i}", disabled=target is None, width="stretch"):
                    v = scripts[target]
                    v["hook_test"] = {"score": r.get("score"), "note": r.get("note", ""), "tested": r.get("tested"),
                                      "swapped": True, "original": {**hooks.hook_of(v), "score": (
                                          v.get("hook_test") or {}).get("score")}}
                    hooks._swap_in(v, r)
                    script.save_scripts(b["id"], scripts)
                    st.toast("Hook applied to the script", icon="✍️")
                    st.rerun()


# ---- posting kit -------------------------------------------------------------------------------

def _kit_downloads(rd: str) -> None:
    items = kit.files(rd)
    if not items:
        return
    st.markdown("**Ready to download**")
    z = Path(rd) / "kit" / "posting-kit.zip"
    if z.exists():
        st.download_button("⬇ Everything (.zip)", z.read_bytes(), file_name="posting-kit.zip", mime="application/zip",
                           type="primary", key=f"kzip_{Path(rd).name}", width="stretch")
    cols = st.columns(3)
    for i, p in enumerate(items):
        mime = {"jpg": "image/jpeg", "mp4": "video/mp4", "srt": "text/plain", "vtt": "text/vtt",
                "txt": "text/plain"}.get(p.suffix[1:], "application/octet-stream")
        cols[i % 3].download_button(p.name, p.read_bytes(), file_name=p.name, mime=mime, key=f"kf_{Path(rd).name}_{p.name}",
                                    width="stretch")


@st.dialog("Posting kit", width="large")
def kit_dialog(b: dict, r: dict) -> None:
    rd = r["dir"]
    v = r.get("variant") or {}
    if not Path(r["path"]).exists():
        with st.spinner("Bringing the video back from cloud storage..."):
            storage.fetch(Path(r["path"]))
    if not Path(r["path"]).exists():
        st.error("The video file isn't on this server or in cloud storage.")
        return
    st.caption("A cover image, a captions file, ready-to-paste text for each platform, and 4:5 / 1:1 versions "
               "for feed posts.")
    frames = run_safely(kit.candidate_frames, rd) or []
    if not frames:
        return
    st.markdown("**1 · Pick the cover moment**")
    idx = st.radio("Scene", range(len(frames)), horizontal=True, format_func=lambda i: f"Scene {i + 1}",
                   label_visibility="collapsed", key=f"kc_{Path(rd).name}")
    st.image([str(p) for _, p in frames], width=96)
    c1, c2 = st.columns([3, 2])
    title = c1.text_input("Title on the cover (optional)", key=f"kt_{Path(rd).name}", placeholder=(
        (v.get("scenes") or [{}])[0].get("overlay") or "")[:60])
    mode = c2.radio("4:5 and 1:1 shape", list(kit.MODES), format_func=lambda m: kit.MODES[m], key=f"km_{Path(rd).name}")
    if st.button("🖼 Make cover, captions file & post text", type="primary", width="stretch"):
        with st.spinner("Making the kit..."):
            res = run_safely(kit.instant, b, rd, frames[idx][0], title, mode)
        if res:
            c = res["captions"]
            st.success(f"Captions file: {c['lines']} lines" + ("" if c["exact"] else " (approximate timing - this video "
                                                                "was made before word timings were saved)"))
    thumbs = sorted((Path(rd) / "kit").glob("thumbnail-*.jpg")) if (Path(rd) / "kit").exists() else []
    if thumbs:
        st.image([str(p) for p in thumbs], width=150, caption=[p.stem.replace("thumbnail-", "") for p in thumbs])
        texts = kit.post_texts(b, v)
        tabs = st.tabs(list(texts))
        for tab, (plat, txt) in zip(tabs, texts.items()):
            with tab:
                st.code(txt, language=None)
    st.markdown("**2 · Re-shaped videos** (Instagram and Facebook feeds)")
    ratios = st.multiselect("Make", ["4:5", "1:1"], ["4:5", "1:1"], key=f"kr_{Path(rd).name}")
    busy = bool(jobs.active(b["id"], {"kit"}))
    if st.button("🎞 Make the videos (runs in the background)", disabled=not ratios or busy, width="stretch"):
        start_task("kit", b["id"], f"{v.get('name', 'Video')} · sizes",
                   {"render_dir": rd, "ratios": ratios, "mode": mode}, note="Making the videos - you can leave this page")
    _kit_downloads(rd)


# ---- calendar ----------------------------------------------------------------------------------

def _due_banner(b: dict, entries: list[dict]) -> None:
    for e in schedule.due(entries):
        with st.container(border=True):
            c1, c2 = st.columns([4, 3], vertical_alignment="center")
            c1.markdown(f"**📣 Time to post:** {t.esc(e['title'])} on {PLATFORM_ICON[e['platform']]} {e['platform']}  \n"
                        f"<span class='bps-muted'>planned for {e['date']} {e['time']}</span>", unsafe_allow_html=True)
            with c2:
                url = st.text_input("Link to the post (optional)", key=f"du_{e['id']}", label_visibility="collapsed",
                                    placeholder="Paste the post's link (optional)")
                a, s, d = st.columns(3)
                if a.button("✅ Posted", key=f"dp_{e['id']}", type="primary", width="stretch"):
                    schedule.update(b["id"], e["id"], status="posted", url=url)
                    st.rerun()
                if s.button("Tomorrow", key=f"dt_{e['id']}", width="stretch"):
                    schedule.update(b["id"], e["id"], date=(date.today() + timedelta(days=1)).isoformat())
                    st.rerun()
                if d.button("Skip", key=f"ds_{e['id']}", width="stretch"):
                    schedule.update(b["id"], e["id"], status="skipped")
                    st.rerun()


def _week_grid(entries: list[dict]) -> None:
    today = date.today()
    first = schedule.week_start(today)
    planned = [schedule.when(e).date() for e in entries if e["status"] != "skipped"]
    last = max([first] + planned)
    weeks = min(8, (schedule.week_start(last) - first).days // 7 + 1)
    for w in range(weeks):
        start = first + timedelta(days=7 * w)
        st.caption(f"Week of {start:%d %b}" + (" · this week" if w == 0 else ""))
        cols = st.columns(7)
        for i, col in enumerate(cols):
            day = start + timedelta(days=i)
            with col, st.container(border=True):
                t.md(f'<div class="bps-muted" style="font-weight:600{";color:#F0B429" if day == today else ""}">'
                     f'{schedule.WEEKDAYS[i]} {day.day}</div>')
                todays = [e for e in entries if e["date"] == day.isoformat() and e["status"] != "skipped"]
                if not todays:
                    st.markdown("&nbsp;", unsafe_allow_html=True)
                for e in sorted(todays, key=lambda e: e["time"]):
                    tone = "green" if e["status"] == "posted" else ""
                    t.md(t.chip(f"{PLATFORM_ICON[e['platform']]} {e['time']}" + (" ✓" if e["status"] == "posted" else ""),
                                tone))
                    st.caption(e["title"][:28])


def calendar_page() -> None:
    b = need_book()
    t.header("Publish · Calendar", "Plan what goes out, and when",
             "Spread your videos over the weeks, get a reminder when it's time, and log each post so Results can "
             "learn from it.")
    renders = [r for r in render.list_renders(b["id"]) if not r.get("draft")]
    entries = schedule.load(b["id"])
    if not renders:
        t.empty("📅", "Render a video first - then plan when to post it.")
        if st.button("Go to Render", type="primary"):
            go("render")
        return
    _due_banner(b, entries)

    used = {e["render"] for e in entries if e["status"] in ("planned", "posted")}
    free = [r for r in renders if Path(r["dir"]).name not in used]
    with st.container(border=True):
        st.markdown("#### 🗓 Plan for me")
        st.caption(f"{len(free)} of {len(renders)} videos aren't scheduled yet. Winners go first, then the videos "
                   "with most views, then the newest.")
        c1, c2, c3 = st.columns(3)
        per_week = c1.number_input("Posts per week", 1, 7, 3)
        weeks = c2.number_input("For how many weeks", 1, 8, 2)
        plats = c3.multiselect("Platforms", kit.PLATFORMS, ["TikTok"])
        tcols = st.columns(max(1, len(plats)))
        times = {p: col.text_input(f"{p} time", schedule.BEST_TIMES[p], key=f"tm_{p}") for p, col in zip(plats, tcols)}
        st.caption("Default times are common starting points (evenings and lunch breaks) - not guarantees. Your Results "
                   "will show what works for your readers.")
        if st.button("Plan my posts", type="primary", disabled=not free or not plats):
            try:
                new = schedule.plan(b["id"], renders, int(per_week), int(weeks), platforms=plats, times=times)
                st.toast(f"{len(new)} posts planned", icon="📅")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    with st.popover("➕ Add a post by hand"):
        pick = st.selectbox("Video", range(len(renders)), format_func=lambda i: (
            (renders[i].get("variant") or {}).get("name") or Path(renders[i]["dir"]).name))
        plat = st.selectbox("Platform", kit.PLATFORMS)
        day = st.date_input("Day", date.today())
        at = st.text_input("Time", schedule.BEST_TIMES[plat])
        note = st.text_input("Note (optional)")
        if st.button("Add", type="primary"):
            try:
                r = renders[pick]
                schedule.add(b["id"], Path(r["dir"]).name, (r.get("variant") or {}).get("name") or "Video", day, at,
                             plat, note)
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    if not entries:
        t.empty("📅", "Nothing planned yet.")
        return
    st.write("")
    _week_grid(entries)

    st.markdown("#### All posts")
    df = pd.DataFrame([{"id": e["id"], "Video": e["title"], "Platform": e["platform"],
                        "Day": date.fromisoformat(e["date"]), "Time": e["time"], "Status": e["status"],
                        "Link": e["url"], "Note": e["note"]} for e in entries])
    edited = st.data_editor(
        df, key="cal_editor", hide_index=True, num_rows="dynamic", width="stretch",
        column_order=["Video", "Platform", "Day", "Time", "Status", "Link", "Note"],
        column_config={"Platform": st.column_config.SelectboxColumn(options=kit.PLATFORMS, required=True),
                       "Status": st.column_config.SelectboxColumn(options=schedule.STATUSES, required=True),
                       "Day": st.column_config.DateColumn(required=True), "Video": st.column_config.TextColumn(disabled=True),
                       "Time": st.column_config.TextColumn(help="24-hour, like 19:00")})
    c1, c2 = st.columns(2)
    if c1.button("💾 Save changes", width="stretch"):
        try:
            keep = set()
            for _, row in edited.dropna(subset=["id"]).iterrows():
                keep.add(row["id"])
                schedule.update(b["id"], row["id"], platform=row["Platform"], date=pd.Timestamp(row["Day"]).date().isoformat(),
                                time=str(row["Time"]), status=row["Status"], url=row["Link"] or "", note=row["Note"] or "")
            for e in entries:
                if e["id"] not in keep:
                    schedule.remove(b["id"], e["id"])
            st.toast("Calendar saved", icon="📅")
            st.rerun()
        except (ValueError, TypeError) as e:
            st.error(f"Couldn't save: {e}")
    c2.download_button("📥 Add to my phone/computer calendar (.ics)", schedule.to_ics(entries, b["title"]),
                       file_name=f"{bk.slug(b['title'])}-posts.ics", mime="text/calendar", width="stretch",
                       disabled=not any(e["status"] == "planned" for e in entries))
    next_step("results", "log views and likes so you can see what works")


# ---- results dashboard ---------------------------------------------------------------------------

def results_page() -> None:
    b = need_book()
    t.header("Publish · Results", "What's working",
             "Log the numbers from each platform. The dashboard shows which hooks, angles, looks and lengths do best "
             "for this book.")
    rs = results.rows(b["id"])
    if not rs:
        t.empty("📈", "Rendered videos appear here.")
        if st.button("Go to Render", type="primary"):
            go("render")
        return
    k = results.kpis(rs)
    t.stats([("Videos", f"{k['made']}", f"{k['logged']} with numbers"),
             ("Total views", f"{k['views']:,.0f}", f"avg {k['avg_views']:,.0f} per video"),
             ("Best video", f"{k['best']['views']:,.0f}" if k["best"] else "-", (k["best"]["name"][:30] if k["best"] else "log some views")),
             ("Engagement", f"{k['engagement'] * 100:.1f}%" if k["engagement"] is not None else "-",
              "likes+comments+shares+saves per view"),
             ("Cost per 1,000 views", f"${k['cost_per_1k']:.2f}" if k["cost_per_1k"] is not None else "-",
              f"${k['total_cost']:.2f} spent making videos")])
    st.write("")
    with st.container(border=True):
        st.markdown("#### 📝 Log your numbers")
        st.caption("Copy them from TikTok / Instagram / YouTube analytics. Leave blank what you don't have.")
        df = pd.DataFrame([{"Video": r["name"], "Made": r["created"], "Hook": r["hook"],
                            "Hook score": r["hook_score"], "Views": r["views"], "Likes": r["likes"],
                            "Comments": r["comments"], "Shares": r["shares"], "Saves": r["saves"],
                            "Link clicks": r["clicks"], "Sales": r["sales"], "🏆": r["winner"]} for r in rs])
        ints = {c: st.column_config.NumberColumn(c, min_value=0, step=1)
                for c in ("Views", "Likes", "Comments", "Shares", "Saves", "Link clicks", "Sales")}
        edited = st.data_editor(df, key="results_editor", hide_index=True, width="stretch", disabled=[
            "Video", "Made", "Hook", "Hook score"], column_config={**ints, "Hook score": st.column_config.NumberColumn(
                format="%.1f")})
        if st.button("💾 Save numbers", type="primary"):
            for i, r in enumerate(rs):
                new = edited.iloc[i]
                cols = {"views": "Views", "likes": "Likes", "comments": "Comments", "shares": "Shares",
                        "saves": "Saves", "clicks": "Link clicks", "sales": "Sales"}
                vals = {m: new[c] for m, c in cols.items()}
                vals["winner"] = bool(new["🏆"])
                old = {m: r[m] for m in cols}
                old["winner"] = r["winner"]
                if any(pd.isna(vals[m]) != (old[m] is None) or (not pd.isna(vals[m]) and vals[m] != old[m])
                       for m in vals):
                    results.save_metrics(r["dir"], **vals)
            st.toast("Saved", icon="📈")
            st.rerun()

    logged = [r for r in rs if r["logged"]]
    if len(logged) < 2:
        st.info("Log the views for at least two videos to see comparisons.")
        return
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("#### Average views by…")
            dim = st.segmented_control("Compare", ["Hook type", "Angle", "Visuals", "Length", "Narrator", "Weekday",
                                                   "Hour"], default="Hook type", label_visibility="collapsed") or "Hook type"
            gs = results.groups(rs, dim)
            if gs:
                cdf = pd.DataFrame({"Average views": [g["avg_views"] for g in gs]},
                                   index=[f"{g['group']} ({g['n']})" for g in gs])
                st.bar_chart(cdf, horizontal=True)
                if any(g["n"] < results.MIN_GROUP for g in gs):
                    st.caption("Groups with one video are just a single result, not a pattern.")
            else:
                st.caption("Nothing to compare yet" + (" - post through the Calendar to learn best days and hours."
                                                       if dim in ("Weekday", "Hour") else "."))
        with st.container(border=True):
            st.markdown("#### Views over time")
            tdf = pd.DataFrame({"Views": [r["views"] for r in sorted(logged, key=lambda r: r["created"])]},
                               index=[f"{r['created']} · {r['name'][:18]}" for r in sorted(logged, key=lambda r: r["created"])])
            st.bar_chart(tdf)
    with right:
        with st.container(border=True):
            st.markdown("#### 💡 What it suggests")
            tips = results.insights(rs)
            if tips:
                for x in tips:
                    st.markdown(f"- {x}")
            else:
                st.caption("No clear pattern yet. Insights appear once each side of a comparison has at least "
                           f"{results.MIN_GROUP} videos with numbers.")
            winners = [r for r in rs if r["winner"]]
            if winners:
                st.caption(f"🏆 {len(winners)} winner(s) - clone them on the Videos page (change one thing at a time).")
            if st.button("🤖 Ask the AI coach (about 1¢)", disabled=len(logged) < 3):
                with st.spinner("Reading your results..."):
                    advice = run_safely(results.coach, b, rs)
                if advice:
                    st.session_state["coach"] = advice
            if st.session_state.get("coach"):
                st.markdown(st.session_state["coach"])
            if len(logged) < 3:
                st.caption("The coach needs numbers for at least 3 videos.")

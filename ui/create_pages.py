"""The making steps: scripts, render, videos."""
import json
import textwrap
import time
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw

from promo import analyze, book as bk, budget, config, jobs, render, script, voice
from promo.genres import GENRES, default_blueprint

from . import theme as t
from .common import (MUSIC_EXT, frame_to_scenes, go, image_price, money, need_book, next_step, run_safely,
                     scenes_frame, start_task, task_panel, video_src)

VISUALS = list(script.VISUAL_TYPES)
MIXES = {"💸 Free only": (True, 0), "⚖️ Balanced": (False, 1), "🎬 Cinematic": (False, 2)}


# ---- storyboard: a free preview of every scene before anything is paid for ------------------------

@st.cache_data(show_spinner=False, max_entries=40)
def _storyboard(book_id: str, stamp: tuple, scenes_json: str) -> list:
    b = bk.load(book_id)
    scenes = json.loads(scenes_json)
    tw, th = 216, 384
    desk = bk.background(b).resize((tw, th))
    small = bk.font("sans", 13)
    tiny = bk.font("bold", 12)
    out = []
    for i, sc in enumerate(scenes):
        vis = sc.get("visual", "cover")
        img = desk.copy()
        d = ImageDraw.Draw(img)
        if vis in ("page", "flip") and bk.path(b, "manuscript"):
            page = bk.preview_page(b, int(sc.get("page") or 1), sc.get("highlight") or "")
            page.thumbnail((int(tw * 0.86), int(th * 0.8)))
            img.paste(page, ((tw - page.width) // 2, (th - page.height) // 2 + 10))
        elif vis == "cover":  # the same 3D book the video shows (a title cover if none was uploaded)
            cov = bk.book_object(b, width=int(tw * 0.6))
            cov.thumbnail((int(tw * 0.62), int(th * 0.6)))
            img.paste(cov, ((tw - cov.width) // 2, (th - cov.height) // 2 + 10), cov)
        else:  # AI photo / AI video / stock / own clip: describe what will be made
            d.rounded_rectangle((10, 60, tw - 10, th - 50), radius=10, fill=(24, 26, 36))
            d.ellipse((tw / 2 - 18, 78, tw / 2 + 18, 114), outline=(240, 180, 41), width=3)  # drawing fonts have no emoji
            d.polygon([(tw / 2 - 6, 86), (tw / 2 - 6, 106), (tw / 2 + 10, 96)], fill=(240, 180, 41))
            d.text((tw / 2, 128), t.VISUAL_LABEL.get(vis, vis).upper(), font=tiny, fill=(240, 180, 41), anchor="mm")
            desc = sc.get("prompt") or sc.get("stock_query") or ""
            if sc.get("character"):
                desc = f"{sc['character']}: {desc}"
            y = 145
            for line in textwrap.wrap(desc, 26)[:11]:
                d.text((20, y), line, font=small, fill=(215, 210, 200))
                y += 16
        ov = (sc.get("overlay") or "").strip()
        if ov:
            lines = textwrap.wrap(ov, 24)[:3]
            h = 8 + 16 * len(lines)
            d.rounded_rectangle((12, 14, tw - 12, 14 + h), radius=6, fill=(255, 255, 255))
            for k, line in enumerate(lines):
                d.text((tw / 2, 22 + 16 * k), line, font=tiny, fill=(20, 20, 20), anchor="mt")
        d.rectangle((0, th - 30, tw, th), fill=(0, 0, 0))
        d.text((8, th - 15), f"{i + 1} · {sc.get('beat', '')}"[:28], font=tiny, fill=(255, 255, 255), anchor="lm")
        d.text((tw - 8, th - 15), f"{t.scene_seconds(sc):.1f}s", font=tiny, fill=(240, 180, 41), anchor="rm")
        out.append(img)
    return out


def storyboard(b: dict, scenes: list[dict]) -> None:
    ms = bk.path(b, "manuscript")
    cov = bk.path(b, "cover")
    stamp = tuple(p.stat().st_mtime if p and p.exists() else 0 for p in (ms, cov, bk.path(b, "background")))
    imgs = run_safely(_storyboard, b["id"], stamp, json.dumps(scenes, sort_keys=True))
    if imgs:
        st.image(imgs, width=132)
        st.caption("Free preview - pages and cover are shown as they'll appear; AI and stock shots show what will "
                   "be made.")


# ---- 5 · Scripts ----------------------------------------------------------------------------

def scripts_page() -> None:
    b = need_book()
    g = GENRES[b["genre"]]
    t.header("Step 5 · Scripts", "Write the videos",
             f"Each script follows the {g['label']} playbook: hook in 2 seconds → feeling → proof from your pages → "
             "soft breadcrumb. Write several, render the best.")

    with st.container(border=True):
        st.markdown("#### ✍️ New scripts")
        bps = analyze.list_blueprints()
        options = ["builtin"] + list(bps)
        pre = st.session_state.pop("bp_choice", None)
        bp_choice = st.selectbox("Format to follow", options, options.index(pre) if pre in options else 0,
                                 format_func=lambda k: f"⭐ Built-in {g['label']} format (proven)" if k == "builtin"
                                 else f"🔁 {bps[k].get('summary', k)[:90]}")
        blueprint = default_blueprint(b["genre"]) if bp_choice == "builtin" else bps[bp_choice]

        c1, c2, c3 = st.columns([2, 3, 2])
        n = c1.number_input("How many scripts", 1, 6, 3)
        mix = c2.segmented_control("Visual mix", list(MIXES), default="⚖️ Balanced",
                                   help="Free only = pages, cover, stock footage and your clips. Balanced = + AI "
                                        "photos and 1 AI video shot. Cinematic = up to 2 AI video shots.") or "⚖️ Balanced"
        free_only, max_ai_video = MIXES[mix]
        c3.markdown(f'<div class="bps-muted" style="margin-top:1.9rem">AI photo ≈ {money(image_price())} · AI video '
                    f'≈ {money(budget.video_cost(config.VIDEO_MODEL, 1))}/s</div>', unsafe_allow_html=True)

        names = [c["name"] for c in b.get("characters", [])]
        feats = b.get("featured") or []
        c1, c2 = st.columns(2)
        focus_chars = c1.multiselect("Characters to feature", names, disabled=free_only or not names,
                                     placeholder="Add characters in step 2" if not names else "Any")
        focus_pages = c2.multiselect("Pages to show", range(len(feats)),
                                     format_func=lambda i: f"p.{feats[i]['page']}: {feats[i]['text'][:55]}",
                                     placeholder="AI picks the best lines" if feats else "Feature pages in step 3")
        notes = st.text_input("Notes for the AI (optional)",
                              placeholder="e.g. focus on the grief angle · it's a Christmas gift · keep under 20s")
        ready = b.get("digest") or b.get("blurb")
        if not ready:
            st.info("Add a blurb or run the AI read-through in Step 1 first.")
        writing = bool(jobs.active(b["id"], {"scripts"}))
        if st.button(f"✨ Write {n} scripts", type="primary", disabled=not ready or writing):
            start_task("scripts", b["id"], f"{n} scripts", {
                "blueprint": blueprint, "source": blueprint.get("source", "builtin"),
                "args": {"n": int(n), "max_ai_video": max_ai_video, "notes": notes,
                         "has_broll": bool(render._broll_clips(b)), "has_stock": bool(config.PEXELS_API_KEY),
                         "focus_characters": focus_chars, "focus_pages": [feats[i] for i in focus_pages],
                         "free_only": free_only}})
        task_panel(b["id"], {"scripts", "variations"})

    scripts = script.load_scripts(b["id"])
    st.write("")
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    c1.markdown(f"#### Your scripts ({len(scripts)})")
    with c2:
        t.legend()
    if not scripts:
        t.empty("✍️", "No scripts yet.")
        return
    for i, v in enumerate(scripts):
        scenes = v.get("scenes", [])
        est = render.estimate(b, v)
        secs = sum(t.scene_seconds(s) for s in scenes)
        with st.container(border=True):
            head, act = st.columns([5, 2], vertical_alignment="top")
            with head:
                t.md(f'<div class="bps-card-title">{t.esc(v.get("name", "Script"))}</div>')
                t.chips([(v.get("hook_type", "hook"), "gold"), (f"{len(scenes)} scenes", ""), (f"~{secs:.0f}s", ""),
                         (f"≤ {money(est['total'])}", "green" if est["total"] < 0.05 else ""),
                         (v.get("created", ""), "")])
                hook = next((s for s in scenes if s.get("voiceover") or s.get("overlay")), {})
                t.md(f'<div class="bps-quote">{t.esc(hook.get("overlay") or hook.get("voiceover"))}</div>')
                st.caption(f"Angle: {v.get('angle', '')}")
            with act:
                if st.button("🎬 Render", key=f"go_{i}", type="primary", width="stretch"):
                    go("render", render_pick=v.get("id"))
                with st.popover("⋯ More", width="stretch"):
                    st.caption(v.get("why_it_will_work", ""))
                    if st.button("📄 Duplicate", key=f"dup_{i}", width="stretch"):
                        copy = {k: val for k, val in v.items() if k != "id"}
                        copy["name"] = v.get("name", "Script") + " (copy)"
                        script.add_scripts(b["id"], [copy], v.get("source", ""))
                        st.rerun()
                    if st.button("🗑 Delete", key=f"del_{i}", width="stretch"):
                        scripts.pop(i)
                        script.save_scripts(b["id"], scripts)
                        st.rerun()
            t.md(t.timeline(scenes))
            if st.toggle("🖼 Storyboard preview (free)", key=f"sb_{v.get('id', i)}"):
                storyboard(b, scenes)
            with st.expander("✏️ Edit scenes, caption & hashtags"):
                names = [c["name"] for c in b.get("characters", [])]
                df = st.data_editor(
                    scenes_frame(v), key=f"ed_{v.get('id', i)}", num_rows="dynamic", width="stretch",
                    hide_index=True,
                    column_config={
                        "visual": st.column_config.SelectboxColumn("visual", options=VISUALS, required=True),
                        "character": st.column_config.SelectboxColumn("character", options=[""] + names),
                        "page": st.column_config.NumberColumn("page", min_value=1, step=1),
                        "flips": st.column_config.NumberColumn("flips", min_value=0, max_value=6, step=1,
                                                               help="Pages turned before landing"),
                        "seconds": st.column_config.NumberColumn("seconds", min_value=1.0, max_value=10.0,
                                                                 help="Only used when the scene has no voiceover"),
                        "voiceover": st.column_config.TextColumn("voiceover", width="large"),
                        "overlay": st.column_config.TextColumn("overlay", width="medium"),
                    })
                cap = st.text_area("Post caption", v.get("post_caption", ""), key=f"cap_{v.get('id', i)}")
                tags = st.text_input("Hashtags", " ".join(v.get("hashtags", [])), key=f"tags_{v.get('id', i)}")
                if st.button("💾 Save changes", key=f"save_{i}", type="primary"):
                    v["scenes"] = frame_to_scenes(df)
                    v["post_caption"], v["hashtags"] = cap, tags.split()
                    script.save_scripts(b["id"], scripts)
                    st.toast("Saved", icon="💾")
                    st.rerun()


# ---- 6 · Render -----------------------------------------------------------------------------

def queue_panel() -> None:
    q = jobs.queue()
    if len(q) > 1:
        with st.expander(f"🎬 Render queue ({len(q)})", expanded=False):
            for k, s in enumerate(q, 1):
                state = "rendering now" if s["state"] == "running" else "waiting"
                st.markdown(f"{k}. **{t.esc(s.get('name'))}** - {state} · _{t.esc(s.get('msg', ''))}_")


def render_page() -> None:
    b = need_book()
    g = GENRES[b["genre"]]
    t.header("Step 6 · Render", "Make the video",
             "Narration, word-by-word captions, page turns, AI shots checked for flaws - assembled into a 9:16 MP4.")
    task_panel(b["id"], jobs.HEAVY)
    queue_panel()
    scripts = script.load_scripts(b["id"])
    if not scripts:
        t.empty("✍️", "Write a script first.")
        if st.button("Go to Scripts", type="primary"):
            go("scripts")
        return

    ids = [v.get("id", str(i)) for i, v in enumerate(scripts)]
    pick = st.session_state.get("render_pick")
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            sel = st.selectbox("Script", range(len(scripts)), ids.index(pick) if pick in ids else 0,
                               format_func=lambda i: f"{scripts[i].get('name')}  ·  {scripts[i].get('created', '')}")
            v = scripts[sel]
            st.session_state["render_pick"] = v.get("id")
            t.md(t.timeline(v.get("scenes", [])))
            storyboard(b, v.get("scenes", []))
            for k, s in enumerate(v.get("scenes", []), 1):
                vis = s.get("visual", "cover")
                extra = f" · p.{s.get('page')}" if vis in ("page", "flip") else (
                    f" · {s.get('character')}" if s.get("character") else "")
                t.md(f'<div class="bps-check"><div class="dot">{k}</div><div class="lbl">'
                     f'<b>{t.VISUAL_ICON.get(vis, "")} {t.esc(s.get("beat", ""))}</b>'
                     f'<span class="bps-muted"> · {t.VISUAL_LABEL.get(vis, vis)}{t.esc(extra)}</span><br>'
                     f'<span class="bps-muted">{t.esc(s.get("voiceover") or s.get("overlay") or "")}</span>'
                     f'</div></div>')

    with right:
        with st.container(border=True):
            st.markdown("#### 🎙 Sound")
            vlist = voice.voices()
            vdefault = voice.default_voice(b["genre"])
            c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
            vname = c1.selectbox(f"Narrator ({config.TTS_PROVIDER})", vlist,
                                 vlist.index(vdefault) if vdefault in vlist else 0)
            if c2.button("▶", help="Hear this voice (~$0.0003)", width="stretch"):
                wav = run_safely(voice.speak, f"This is the voice for {b['title']}.", vname, g["voice_instructions"],
                                 bk.book_dir(b["id"]), b["genre"])
                if wav:
                    st.audio(str(wav), autoplay=True)
            tracks = sorted(p for p in config.MUSIC_DIR.glob("*") if p.suffix.lower() in MUSIC_EXT)
            music = st.selectbox("Music", [None] + tracks, format_func=lambda p: "No music" if p is None else p.name)
            vol = st.slider("Music volume", 0.05, 0.6, 0.25, 0.05, disabled=music is None)
            with st.popover("➕ Add a music track", width="stretch"):
                up = st.file_uploader(f"Royalty-free, {g['music_mood']} mood fits", list(e[1:] for e in MUSIC_EXT))
                if up and st.button("Save track", type="primary"):
                    (config.MUSIC_DIR / Path(up.name).name).write_bytes(up.getbuffer())
                    st.rerun()
            c1, c2 = st.columns(2)
            captions = c1.toggle("Captions", True)
            page_sound = c2.toggle("Page-turn sound", True)

        with st.container(border=True):
            st.markdown("#### 🔍 AI quality check")
            quality = st.toggle("Check every AI shot + look through the video", True,
                                help="A vision AI looks for warped hands/faces, garbled text, melting objects and "
                                     "character mismatch; flawed shots are re-made before the final file.")
            video_retries = st.segmented_control("Re-make a flawed AI video up to", [0, 1, 2], default=1,
                                                 format_func=lambda n: f"{n}×", disabled=not quality)
            video_retries = 1 if video_retries is None else video_retries
            draft = st.toggle("Draft quality (720p, about twice as fast)", False,
                              help="Great for checking a script. Render the final in full quality once you like it - "
                                   "AI shots and voice are reused, so the final costs nothing extra.")

        est = render.estimate(b, v, quality)
        left_budget = budget.remaining()
        with st.container(border=True):
            parts = [("Voice", est["voice"]), ("AI photos", est["images"]), ("AI video", est["ai_video"])]
            if quality:
                parts.append(("Quality check", est["quality_check"]))
            t.md(f'<div class="bps-muted">Estimated cost (upper bound)</div>'
                 f'<div style="font:700 2rem Fraunces,serif">{money(est["total"])}</div>'
                 + "".join(t.chip(f"{k} {money(x)}") for k, x in parts if x)
                 + f'<div class="bps-muted" style="margin-top:.4rem">Budget left: {money(left_budget)} · shots '
                   f'already made are reused free</div>')
            busy = bool(jobs.queue())
            over = est["total"] > left_budget
            opts = {"voice_name": vname, "captions": captions, "music": str(music) if music else None,
                    "music_volume": vol, "page_sound": page_sound, "quality_check": quality,
                    "video_retries": video_retries, "draft": draft}
            label = ("➕ Add to render queue" if busy else "🎬 Render video") + (" (draft)" if draft else "")
            if st.button(label, type="primary", width="stretch", disabled=over):
                jobs.start_render(b["id"], v, opts)
                st.toast("Added to the queue" if busy else "Rendering started - a few minutes", icon="🎬")
                time.sleep(0.8)
                st.rerun()
            if busy:
                st.caption("Renders run one at a time; this one will start when the others finish.")
            with st.popover("🎬 Render several scripts", width="stretch"):
                many = st.multiselect("Scripts to queue (same sound & quality settings)", range(len(scripts)),
                                      format_func=lambda i: scripts[i].get("name", f"Script {i + 1}"))
                if st.button(f"Queue {len(many)} render(s)", type="primary", disabled=not many or over):
                    for i in many:
                        jobs.start_render(b["id"], scripts[i], opts)
                    st.toast(f"{len(many)} renders queued", icon="🎬")
                    time.sleep(0.8)
                    st.rerun()
            if over:
                st.warning("Over your monthly budget - choose the 💸 Free only mix when writing scripts.")
    next_step("videos", "download, post, and log how each video does")


# ---- 7 · Videos -----------------------------------------------------------------------------

def quality_report(q: dict | None) -> None:
    if not q:
        st.caption("Rendered without the quality check.")
        return
    shots, final = q.get("shots") or [], q.get("final") or {}
    if final.get("summary"):
        st.markdown(f"**Final look-through:** {final['summary']}")
    for s in shots:
        takes = s.get("takes", [])
        line = " → ".join(f"{x['score']}/10" for x in takes)
        probs = "; ".join(p for x in takes[:-1] for p in x.get("problems", [])[:2])
        st.markdown(f"- **{s['scene']}** ({s['kind']}): {line}" + (f" - fixed: _{probs}_" if probs else ""))
    for rm in final.get("remade") or []:
        st.markdown(f"- **Scene {rm['scene']}** re-made after the final check: _{'; '.join(rm['problems'][:3])}_")
    if not shots and not final:
        st.caption("No AI shots in this video.")


def _quality_chip(q: dict | None) -> tuple[str, str]:
    if not q:
        return ("QA off", "")
    scores = [s.get("final_score", 0) for s in q.get("shots") or []]
    scores += [v for k, v in ((q.get("final") or {}).get("scores") or {}).items()]
    fixed = sum(1 for s in q.get("shots") or [] if s.get("fixed")) + len((q.get("final") or {}).get("remade") or [])
    if not scores:
        return ("✓ QA", "green")
    low = min(scores)
    return (f"QA low {low}/10" + (f" · {fixed} fixed" if fixed else ""), "green" if low >= 7 else "red")


def videos_page() -> None:
    b = need_book()
    t.header("Step 7 · Videos", "Post, measure, clone the winner",
             "Post several, log their views, then make variations of the best one that change ONE thing.")
    task_panel(b["id"], jobs.HEAVY | {"variations"})
    renders = render.list_renders(b["id"])
    if not renders:
        t.empty("🎬", "Rendered videos appear here.")
        if st.button("Go to Render", type="primary"):
            go("render")
        return
    show = st.segmented_control("Show", ["All", "🏆 Winners", "Not logged"], default="All") or "All"
    if show == "🏆 Winners":
        renders = [r for r in renders if r.get("winner")]
    elif show == "Not logged":
        renders = [r for r in renders if not r.get("views")]

    for row in range(0, len(renders), 3):
        cols = st.columns(3)
        for col, r in zip(cols, renders[row:row + 3]):
            v, k = r["variant"], r["dir"]
            with col, st.container(border=True):
                fname = f"{bk.slug(b['title'])}-{bk.slug(v.get('name', 'video'))}.mp4"
                src = video_src(r["path"])
                if src:
                    st.video(src)
                else:
                    st.caption("🎬 Video file not found on this server or in cloud storage.")
                t.md(f'<div class="bps-card-title">{"🏆 " if r.get("winner") else ""}{t.esc(v.get("name"))}</div>')
                t.chips([(f"{r['seconds']:.0f}s", ""), (money(r.get("cost", 0)), ""), _quality_chip(r.get("quality")),
                         (f"👁 {r.get('views', 0):,}", "gold" if r.get("views") else "")]
                        + ([("Draft 720p", "blue")] if r.get("draft") else []))
                if r.get("warnings"):
                    st.caption(f"⚠ {len(r['warnings'])} note(s) - see Details")
                if Path(r["path"]).exists():
                    st.download_button("⬇ Download MP4", Path(r["path"]).read_bytes(), type="primary",
                                       file_name=fname, mime="video/mp4", key=f"dl_{k}", width="stretch")
                elif src:  # lives in cloud storage: download straight from there
                    st.link_button("⬇ Download MP4", video_src(r["path"], fname), type="primary", width="stretch")
                c1, c2 = st.columns(2)
                with c1.popover("📋 Caption", width="stretch"):
                    st.code(f"{v.get('post_caption', '')}\n\n{' '.join(v.get('hashtags', []))}", language=None)
                with c2.popover("📈 Results", width="stretch"):
                    views = st.number_input("Views", 0, value=int(r.get("views", 0)), key=f"views_{k}")
                    likes = st.number_input("Likes", 0, value=int(r.get("likes", 0)), key=f"likes_{k}")
                    winner = st.checkbox("🏆 Winner", r.get("winner", False), key=f"win_{k}")
                    if st.button("Save", key=f"savestats_{k}", type="primary", width="stretch"):
                        render.update_render(k, views=views, likes=likes, winner=winner)
                        st.rerun()
                c1, c2 = st.columns(2)
                with c1.popover("🔁 Redo a scene", width="stretch"):
                    scenes = v.get("scenes", [])
                    redo_ok = [i for i, sc in enumerate(scenes) if sc.get("visual") in
                               ("ai_image", "character", "ai_video", "stock")]
                    if not redo_ok:
                        st.caption("This video has no AI or stock shots to redo - edit the script instead.")
                    else:
                        si = st.selectbox("Scene", redo_ok, key=f"rs_{k}", format_func=lambda i: (
                            f"{i + 1} · {scenes[i].get('beat', '')} · {t.VISUAL_LABEL.get(scenes[i].get('visual'), '')}"))
                        cur = scenes[si].get("stock_query") if scenes[si].get("visual") == "stock" else scenes[si].get("prompt")
                        new_prompt = st.text_area("What should it show? (leave as is for a fresh take)", cur or "",
                                                  key=f"rp_{k}_{si}", height=110)
                        st.caption("Makes a new version of the video; only this shot is re-made (voice and other "
                                   "shots are reused), so it costs about one AI shot.")
                        if st.button("Make new version", type="primary", key=f"redo_{k}", width="stretch"):
                            start_task("redo", b["id"], f"{v.get('name')} · scene {si + 1}",
                                       {"render_dir": k, "scene": si, "prompt": new_prompt})
                with c2.popover("🗑 Delete", width="stretch"):
                    st.caption("Deletes this video here and in cloud storage.")
                    if st.button("Delete video", key=f"delv_{k}", type="primary", width="stretch"):
                        run_safely(render.delete_render, k)
                        st.toast("Video deleted", icon="🗑")
                        st.rerun()
                with st.expander("Details & quality report"):
                    for w in r.get("warnings", []):
                        st.caption(f"⚠ {w}")
                    quality_report(r.get("quality"))
                    st.caption(f"Made {r['created']} · voice {r.get('voice')}"
                               + (f" · new version of {r['redo_of']}" if r.get("redo_of") else ""))
                if r.get("winner"):
                    change = st.selectbox("Clone, changing only…", [
                        "the hook (first line + first overlay)", "the footage / visuals",
                        "the pacing (faster cuts)", "the angle wording, same structure"], key=f"chg_{k}")
                    if st.button("🧬 Make 3 variations", key=f"clone_{k}", width="stretch"):
                        start_task("variations", b["id"], f"Variations of {v.get('name')}",
                                   {"winner": v, "change": change})

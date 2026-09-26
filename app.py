"""Book Promo Studio - turn a book into realistic, faceless TikTok / Reels / Shorts videos.

Run with:  run.bat   (or: .venv\\Scripts\\streamlit run app.py)
"""
import hmac
import importlib
import json
import os
import re
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from promo import analyze, book as bk, budget, config, ingest, jobs, render, script, visuals, voice
from promo.genres import GENRES, default_blueprint

st.set_page_config(page_title="Book Promo Studio", page_icon="📚", layout="wide")

VISUALS = list(script.VISUAL_TYPES)
WEB = os.name != "nt"  # running on a Linux web server rather than the Windows PC
MUSIC_EXT = (".mp3", ".wav", ".m4a", ".aac", ".ogg")


# ---- helpers ---------------------------------------------------------------------------

def money(x: float) -> str:
    return f"${x:,.3f}" if x < 1 else f"${x:,.2f}"


def reload_config() -> None:
    importlib.reload(config)


def save_env(values: dict) -> None:
    env_path = config.ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    current = {l.split("=", 1)[0].strip(): i for i, l in enumerate(lines) if "=" in l and not l.startswith("#")}
    for k, v in values.items():
        os.environ[k] = v
        if k in current:
            lines[current[k]] = f"{k}={v}"
        else:
            lines.append(f"{k}={v}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reload_config()


def run_safely(fn, *args, **kwargs):
    """Call fn and show a friendly error instead of a stack trace."""
    try:
        return fn(*args, **kwargs)
    except budget.BudgetExceeded as e:
        st.error(f"💰 Budget guard stopped this: {e}")
    except Exception as e:
        st.error(f"Something went wrong: {e}")
    return None


def save_upload(upload, folder: Path, name: str) -> str:
    ext = Path(upload.name).suffix.lower()
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{name}.*"):
        old.unlink()
    (folder / f"{name}{ext}").write_bytes(upload.getbuffer())
    return f"{name}{ext}"


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?\"”])\s+", " ".join(text.split()))
    return [p.strip() for p in parts if 4 <= len(p.split()) <= 60]


def cost_hint() -> str:
    img = budget.image_cost(config.IMAGE_MODEL, config.IMAGE_QUALITY)
    vid = budget.video_cost(config.VIDEO_MODEL, 1)
    return f"AI photo ≈ {money(img)} each · AI video ≈ {money(vid)}/second · pages, cover & stock footage are free"


# ---- sidebar: budget + settings -------------------------------------------------------------

def sidebar() -> None:
    with st.sidebar:
        st.title("📚 Book Promo Studio")
        spent, cap = budget.spent_this_month(), config.MONTHLY_BUDGET_USD
        st.metric("Spent this month", money(spent), f"{money(max(0, cap - spent))} left of {money(cap)}",
                  delta_color="off")
        st.progress(min(1.0, spent / cap) if cap else 1.0)

        missing = [k for k in ("OPENAI_API_KEY", "XAI_API_KEY") if not getattr(config, k)]
        if missing:
            st.warning("Add your API keys below to start: " + ", ".join(missing))
        if not config.PEXELS_API_KEY:
            st.info("Tip: add a free Pexels key (pexels.com/api) for realistic stock footage at $0.")

        with st.expander("⚙️ Settings & API keys", expanded=bool(missing)):
            with st.form("settings"):
                def key_input(label: str, attr: str) -> str:  # never send a saved key back to the browser
                    saved = "saved ✓ - leave blank to keep" if getattr(config, attr) else ""
                    return st.text_input(label, type="password", placeholder=saved)

                keys = {
                    "OPENAI_API_KEY": key_input("OpenAI API key", "OPENAI_API_KEY"),
                    "XAI_API_KEY": key_input("xAI (Grok) API key", "XAI_API_KEY"),
                    "PEXELS_API_KEY": key_input("Pexels API key (free, optional)", "PEXELS_API_KEY"),
                }
                vals = {
                    "MONTHLY_BUDGET_USD": str(st.number_input("Monthly budget (USD)", 1.0, 500.0,
                                                              float(config.MONTHLY_BUDGET_USD), 1.0)),
                    "LLM_PROVIDER": st.selectbox("Script writer", ["openai", "xai"],
                                                 ["openai", "xai"].index(config.LLM_PROVIDER),
                                                 help="openai = gpt-5-mini (cheapest), xai = Grok"),
                    "IMAGE_PROVIDER": st.selectbox("AI photos", ["openai", "xai"],
                                                   ["openai", "xai"].index(config.IMAGE_PROVIDER)),
                    "IMAGE_QUALITY": st.selectbox("AI photo quality (OpenAI)", ["low", "medium", "high"],
                                                  ["low", "medium", "high"].index(config.IMAGE_QUALITY)),
                    "TTS_PROVIDER": st.selectbox("Narration voice", ["xai", "openai"],
                                                 ["xai", "openai"].index(config.TTS_PROVIDER),
                                                 help="xai = Grok voices (cheapest), openai = gpt-4o-mini-tts"),
                    "VIDEO_PROVIDER": st.selectbox("AI video", ["xai", "openai"],
                                                   ["xai", "openai"].index(config.VIDEO_PROVIDER),
                                                   help="xai = Grok Imagine (cheapest), openai = Sora 2"),
                }
                if st.form_submit_button("Save settings"):
                    for k in ("LLM_MODEL", "IMAGE_MODEL", "VIDEO_MODEL", "TTS_MODEL"):  # let defaults follow the provider
                        os.environ.pop(k, None)
                    vals.update({k: v for k, v in keys.items() if v.strip()})
                    save_env({k: v.strip() for k, v in vals.items()})
                    st.success("Saved.")
                    st.rerun()
            if WEB:
                st.caption("Web version: keys typed here last until the app restarts. Put them in the app's "
                           "Secrets for good.")
            st.caption(f"Models: {config.LLM_MODEL} · {config.IMAGE_MODEL} ({config.IMAGE_QUALITY}) · "
                       f"{config.VIDEO_MODEL} · {config.TTS_MODEL}")

        with st.expander("🧾 Spending log"):
            rows = budget.recent(40)
            if rows:
                st.dataframe(pd.DataFrame(rows)[["ts", "service", "model", "cost", "note"]], hide_index=True)
            else:
                st.caption("Nothing spent yet.")


# ---- tab 1: book --------------------------------------------------------------------------

def pick_book() -> dict | None:
    books = bk.list_books()
    ids = list(books)
    current = st.session_state.get("book_id")
    options = ids + ["➕ New book"]
    idx = ids.index(current) if current in ids else (0 if ids else len(options) - 1)
    choice = st.selectbox("Book", options, idx, format_func=lambda i: books[i]["title"] if i in books else i)
    if choice == "➕ New book":
        with st.form("new_book"):
            title = st.text_input("Book title")
            genre = st.selectbox("Genre", list(GENRES), format_func=lambda g: GENRES[g]["label"])
            if st.form_submit_button("Create book", type="primary") and title.strip():
                b = bk.new_book(title.strip())
                b["genre"] = genre
                bk.save(b)
                st.session_state["book_id"] = b["id"]
                st.rerun()
        return None
    st.session_state["book_id"] = choice
    return bk.load(choice)


def tab_book(b: dict) -> None:
    left, right = st.columns([3, 2])
    with left:
        with st.form("book_details"):
            st.subheader("Book details")
            b["title"] = st.text_input("Title", b["title"])
            b["author"] = st.text_input("Author / pen name", b.get("author", ""))
            keys = list(GENRES)
            b["genre"] = st.selectbox("Genre - decides the angle, hooks, voice, pacing and look", keys,
                                      keys.index(b["genre"]), format_func=lambda g: GENRES[g]["label"])
            b["blurb"] = st.text_area("Blurb / what the book is about", b.get("blurb", ""), height=110)
            b["audience"] = st.text_input("Who is it for?", b.get("audience", ""),
                                          placeholder="e.g. dads who find it hard to say 'I love you'")
            c1, c2 = st.columns(2)
            b["where_to_buy"] = c1.text_input("Where to buy", b.get("where_to_buy", "Amazon"))
            b["link"] = c2.text_input("Link (for your caption)", b.get("link", ""))
            if st.form_submit_button("Save details", type="primary"):
                bk.save(b)
                st.success("Saved.")

        g = GENRES[b["genre"]]
        with st.expander(f"🎯 The {g['label']} playbook (what the AI will follow)"):
            st.markdown("**Angles:**\n" + "\n".join(f"- {a}" for a in g["angles"]))
            st.markdown("**Hook style:**\n" + "\n".join(f"- _{h}_" for h in g["hook_examples"]))
            st.markdown(f"**Tone:** {g['tone']}  \n**Voice:** {voice.default_voice(b['genre'])} -{g['voice_instructions']}  \n"
                        f"**Length:** ~{g['target_seconds']}s · **Ending:** {g['breadcrumb'].format(title=b['title'])}  \n"
                        f"**Rules:** {g['rules']}")

    with right:
        st.subheader("Cover & manuscript")
        thumb = bk.cover_thumb(b, 260)
        if thumb:
            st.image(thumb)
        up = st.file_uploader("Book cover (front)", ["png", "jpg", "jpeg", "webp"], key=f"cover_{b['id']}")
        if up and st.button("Use this cover"):
            b["cover"] = save_upload(up, bk.book_dir(b["id"]), "cover")
            bk.save(b)
            st.rerun()

        ms = bk.path(b, "manuscript")
        if ms and ms.exists():
            st.success(f"Manuscript: {ms.name} · {bk.page_count(b)} pages")
        up = st.file_uploader("Manuscript (PDF, DOCX or TXT)", ["pdf", "docx", "txt", "md"], key=f"ms_{b['id']}")
        if up and st.button("Use this manuscript"):
            b["manuscript"] = save_upload(up, bk.book_dir(b["id"]), "manuscript")
            (bk.book_dir(b["id"]) / "pages.json").unlink(missing_ok=True)
            b["digest"] = None
            bk.save(b)
            st.rerun()

        st.markdown("**Desk / background** (what the pages and book lie on)")
        bg = bk.path(b, "background")
        if bg and bg.exists():
            st.image(str(bg), width=160)
        c1, c2 = st.columns(2)
        if c1.button(f"✨ AI desk photo ({money(budget.image_cost(config.IMAGE_MODEL, config.IMAGE_QUALITY))})"):
            with st.spinner("Creating a desk photo..."):
                if run_safely(visuals.make_background, b):
                    st.rerun()
        up = c2.file_uploader("…or your own photo", ["png", "jpg", "jpeg"], key=f"bg_{b['id']}",
                              label_visibility="collapsed")
        if up and c2.button("Use photo"):
            b["background"] = save_upload(up, bk.book_dir(b["id"]), "background")
            bk.save(b)
            st.rerun()

        st.markdown("**Your own video clips** (optional B-roll: you reading, your desk, the printed book)")
        broll_dir = bk.book_dir(b["id"]) / "broll"
        clips = render._broll_clips(b)
        if clips:
            st.caption(", ".join(c.name for c in clips))
        ups = st.file_uploader("Add clips", ["mp4", "mov", "m4v", "webm"], accept_multiple_files=True,
                               key=f"broll_{b['id']}", label_visibility="collapsed")
        if ups and st.button("Save clips"):
            broll_dir.mkdir(exist_ok=True)
            for u in ups:
                (broll_dir / Path(u.name).name).write_bytes(u.getbuffer())
            st.rerun()

    st.divider()
    st.subheader("🧠 AI read-through of your manuscript")
    st.caption("Finds the emotional promise, target readers, characters and the most scroll-stopping lines "
               "(with page numbers). Costs about $0.01-0.03 once per book.")
    if st.button("Read my manuscript", type="primary", disabled=not (ms and ms.exists())):
        with st.spinner("Reading the book..."):
            if run_safely(bk.build_digest, b):
                st.rerun()
    d = b.get("digest")
    if d:
        c1, c2 = st.columns(2)
        c1.markdown(f"**Summary:** {d.get('summary', '')}\n\n**Emotional promise:** {d.get('emotional_promise', '')}")
        c1.markdown("**Readers who'll love it:** " + "; ".join(d.get("target_readers", [])))
        c2.markdown("**Hooks / tropes:** " + "; ".join(d.get("tropes_or_hooks", [])))
        c2.markdown("**Comparable books:** " + "; ".join(d.get("comparable_books", [])))
        quotes = d.get("quotes", [])
        if quotes:
            st.dataframe(pd.DataFrame(quotes)[["page", "text", "why"]], hide_index=True, width="stretch")


# ---- tab 2: characters & pages ---------------------------------------------------------------

def tab_characters_pages(b: dict) -> None:
    st.subheader("🎭 Characters to show in the videos")
    st.caption("Add a photo to keep the same face in every AI shot, or let the AI create a portrait once "
               f"({money(budget.image_cost(config.IMAGE_MODEL, config.IMAGE_QUALITY))}). "
               "Real people: only use photos you have permission to use.")
    chars = b.setdefault("characters", [])
    for i, c in enumerate(list(chars)):
        cols = st.columns([1, 4, 2])
        ref = bk.book_dir(b["id"]) / c["ref_image"] if c.get("ref_image") else None
        if ref and ref.exists():
            cols[0].image(str(ref), width=110)
        else:
            cols[0].markdown("🧑 _no photo_")
        cols[1].markdown(f"**{c['name']}**  \n{c.get('description', '')}")
        if cols[2].button("✨ AI portrait", key=f"port_{i}"):
            with st.spinner(f"Creating {c['name']}..."):
                img = run_safely(visuals.make_character_reference, b, c)
                if img:
                    c["ref_image"] = str(img.relative_to(bk.book_dir(b["id"]))).replace("\\", "/")
                    bk.save(b)
                    st.rerun()
        if cols[2].button("🗑 Remove", key=f"delc_{i}"):
            chars.pop(i)
            bk.save(b)
            st.rerun()

    with st.form("add_char", clear_on_submit=True):
        st.markdown("**Add a character**")
        c1, c2 = st.columns([2, 3])
        name = c1.text_input("Name")
        photo = c1.file_uploader("Reference photo (optional)", ["png", "jpg", "jpeg", "webp"])
        desc = c2.text_area("Look + personality", height=120,
                            placeholder="e.g. 30s, Nigerian, short natural hair, gold hoop earrings, tired kind eyes, "
                                        "wears a nurse's uniform; quiet but fierce")
        if st.form_submit_button("Add character", type="primary") and name.strip():
            c = {"name": name.strip(), "description": desc.strip()}
            if photo:
                c["ref_image"] = "characters/" + save_upload(photo, bk.book_dir(b["id"]) / "characters",
                                                             bk.slug(name))
            chars.append(c)
            bk.save(b)
            st.rerun()
    found = [c for c in (b.get("digest") or {}).get("characters", [])
             if c.get("name", "").lower() not in {x["name"].lower() for x in chars}]
    if found and st.button(f"Import {len(found)} character(s) the AI found in the manuscript"):
        chars.extend({"name": c["name"], "description": c.get("description", "")} for c in found)
        bk.save(b)
        st.rerun()

    st.divider()
    st.subheader("📖 Pages to show (page-to-page)")
    if not bk.path(b, "manuscript"):
        st.info("Upload the manuscript on the Book tab first.")
        return
    n = bk.page_count(b)
    all_pages = {p["page"]: p["text"] for p in bk.pages(b)}
    c1, c2 = st.columns([2, 3])
    with c1:
        if st.session_state.get("pick_page", 1) > max(1, n):
            st.session_state["pick_page"] = 1
        page = st.number_input("Page", 1, max(1, n), key="pick_page")
        opts = sentences(all_pages.get(page, ""))
        pick = st.selectbox("Line to highlight", ["(type my own)"] + opts, key=f"line_{page}")
        line = st.text_area("Highlight text (copy exactly from the page)",
                            "" if pick == "(type my own)" else pick, key=f"hl_{page}_{pick}", height=100)
        if st.button("⭐ Feature this page + line", type="primary"):
            b.setdefault("featured", []).append({"page": int(page), "text": line.strip()})
            bk.save(b)
            st.rerun()
        st.caption("Featured pages are used first when the AI writes scripts. In the video the previous pages turn, "
                   "then the line is highlighted while the camera pushes in.")
    with c2:
        img = run_safely(bk.preview_page, b, int(page), line.strip())
        if img is not None:
            st.image(img, width=420)

    feats = b.get("featured") or []
    if feats:
        st.markdown("**Featured pages**")
        for i, f in enumerate(list(feats)):
            cols = st.columns([1, 8, 1])
            cols[0].markdown(f"p.{f['page']}")
            cols[1].markdown(f"_{f['text'] or '(whole page)'}_")
            if cols[2].button("✕", key=f"delf_{i}"):
                feats.pop(i)
                bk.save(b)
                st.rerun()


# ---- tab 3: reference formats (blueprints) -------------------------------------------------------

def tab_formats(b: dict) -> None:
    st.subheader("🔁 Copy the format of a viral video (optional)")
    st.caption("Paste a TikTok / Reels / YouTube Shorts link of a book video that went viral. The app studies its "
               "structure (hook, pacing, overlays, ending) - never its words - so your scripts can follow a proven "
               "format. Transcription runs free on your PC; the AI analysis costs about $0.01.")
    c1, c2 = st.columns(2)
    url = c1.text_input("Video link")
    up = c2.file_uploader("…or upload the video file", ["mp4", "mov", "webm"])
    if st.button("Analyze format", type="primary", disabled=not (url or up)):
        with st.status("Analyzing the reference video...", expanded=True) as stt:
            def step(msg):
                stt.write(msg)
            try:
                if up:
                    tmp = config.REFS_DIR / Path(up.name).name
                    tmp.write_bytes(up.getbuffer())
                    video = ingest.import_local(tmp, up.name)
                    tmp.unlink(missing_ok=True)
                else:
                    step("Downloading...")
                    video = ingest.download(url.strip())
                bp = analyze.analyze_reference(video, progress=step)
                stt.update(label=f"Blueprint ready: {bp.get('summary', '')}", state="complete")
            except Exception as e:
                stt.update(label=f"Failed: {e}", state="error")

    bps = analyze.list_blueprints()
    if not bps:
        st.info("No reference videos yet. You can still make videos with the built-in genre blueprint.")
    for bp_id, bp in bps.items():
        sc = bp.get("score", {})
        with st.expander(f"{bp.get('summary', bp_id)}  ·  hook {sc.get('hook', '?')}/10"):
            st.markdown(f"**Source:** {bp.get('source')}  \n**Hook:** {bp.get('hook', {}).get('type')} - "
                        f"{bp.get('hook', {}).get('mechanic')}  \n**Why it works:** {bp.get('why_it_works')}  \n"
                        f"**Best for:** {', '.join(bp.get('best_for_genres', []))}")
            st.dataframe(pd.DataFrame(bp.get("structure", [])), hide_index=True, width="stretch")
            if st.button("Delete", key=f"delbp_{bp_id}"):
                (config.BLUEPRINTS_DIR / f"{bp_id}.json").unlink(missing_ok=True)
                st.rerun()


# ---- tab 4: scripts -------------------------------------------------------------------------

def scenes_frame(v: dict) -> pd.DataFrame:
    cols = ["beat", "visual", "voiceover", "overlay", "page", "highlight", "flips", "character", "prompt",
            "stock_query", "seconds"]
    rows = [{c: s.get(c) for c in cols} for s in v.get("scenes", [])]
    return pd.DataFrame(rows, columns=cols)


def frame_to_scenes(df: pd.DataFrame) -> list[dict]:
    out = []
    for rec in df.to_dict("records"):
        s = {}
        for k, val in rec.items():
            if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
                continue
            if k in ("page", "flips"):
                val = int(val)
            elif k == "seconds":
                val = float(val)
            s[k] = val
        s.setdefault("visual", "cover")
        s.setdefault("voiceover", "")
        s.setdefault("overlay", "")
        out.append(s)
    return out


def tab_scripts(b: dict) -> None:
    st.subheader("✍️ Write video scripts")
    bps = analyze.list_blueprints()
    options = ["builtin"] + list(bps)
    bp_choice = st.selectbox("Format to follow", options, format_func=lambda k: (
        f"Built-in {GENRES[b['genre']]['label']} format (proven)" if k == "builtin"
        else f"From reference: {bps[k].get('summary', k)[:90]}"))
    blueprint = default_blueprint(b["genre"]) if bp_choice == "builtin" else bps[bp_choice]

    c1, c2, c3 = st.columns(3)
    n = c1.slider("How many different scripts", 1, 6, 3)
    free_only = c2.toggle("Free visuals only", help="Only pages, cover, stock footage and your own clips - $0 "
                                                    "except the voice (~$0.005).")
    max_ai_video = 0 if free_only else c3.slider("AI video shots per script", 0, 2, 1,
                                                 help="The most realistic but the priciest part.")
    st.caption(cost_hint())

    names = [c["name"] for c in b.get("characters", [])]
    feats = b.get("featured") or []
    c1, c2 = st.columns(2)
    focus_chars = c1.multiselect("Characters to feature", names, disabled=free_only or not names,
                                 help="Add characters on the 'Characters & pages' tab.")
    feat_labels = [f"p.{f['page']}: {f['text'][:60]}" for f in feats]
    focus_pages = c2.multiselect("Pages to show", range(len(feats)), format_func=lambda i: feat_labels[i],
                                 help="Pick pages on the 'Characters & pages' tab. Leave empty to let the AI choose "
                                      "from its best quotes.")
    notes = st.text_area("Extra notes for the AI (optional)",
                         placeholder="e.g. focus on the grief angle; mention it's a Christmas gift; keep under 20s")

    ready = b.get("digest") or b.get("blurb")
    if not ready:
        st.info("Fill in the blurb or run 'Read my manuscript' on the Book tab first.")
    if st.button(f"Write {n} scripts", type="primary", disabled=not ready):
        with st.spinner("Writing scripts..."):
            variants = run_safely(script.generate, b, blueprint, n=n, max_ai_video=max_ai_video, notes=notes,
                                  has_broll=bool(render._broll_clips(b)), has_stock=bool(config.PEXELS_API_KEY),
                                  focus_characters=focus_chars, focus_pages=[feats[i] for i in focus_pages],
                                  free_only=free_only)
            if variants:
                script.add_scripts(b["id"], variants, blueprint.get("source", "builtin"))
                st.rerun()

    scripts = script.load_scripts(b["id"])
    if not scripts:
        return
    st.divider()
    st.subheader(f"Your scripts ({len(scripts)})")
    for i, v in enumerate(scripts):
        est = render.estimate(b, v)
        with st.expander(f"**{v.get('name', 'Script')}** · {v.get('hook_type', '')} · {len(v.get('scenes', []))} "
                         f"scenes · up to {money(est['total'])} · {v.get('created', '')}"):
            st.markdown(f"**Angle:** {v.get('angle', '')}  \n**Why it should work:** {v.get('why_it_will_work', '')}")
            df = st.data_editor(
                scenes_frame(v), key=f"ed_{v.get('id', i)}", num_rows="dynamic", width="stretch",
                hide_index=True,
                column_config={
                    "visual": st.column_config.SelectboxColumn("visual", options=VISUALS, required=True),
                    "character": st.column_config.SelectboxColumn("character", options=[""] + names),
                    "page": st.column_config.NumberColumn("page", min_value=1, step=1),
                    "flips": st.column_config.NumberColumn("flips", min_value=0, max_value=6, step=1,
                                                           help="Pages turned before landing (page/flip scenes)"),
                    "seconds": st.column_config.NumberColumn("seconds", min_value=1.0, max_value=10.0,
                                                             help="Only used when the scene has no voiceover"),
                    "voiceover": st.column_config.TextColumn("voiceover", width="large"),
                    "overlay": st.column_config.TextColumn("overlay", width="medium"),
                })
            cap = st.text_area("Post caption", v.get("post_caption", ""), key=f"cap_{v.get('id', i)}")
            tags = st.text_input("Hashtags", " ".join(v.get("hashtags", [])), key=f"tags_{v.get('id', i)}")
            c1, c2, c3 = st.columns(3)
            if c1.button("💾 Save changes", key=f"save_{i}"):
                v["scenes"] = frame_to_scenes(df)
                v["post_caption"], v["hashtags"] = cap, tags.split()
                script.save_scripts(b["id"], scripts)
                st.success("Saved.")
            if c2.button("🎬 Render this one", key=f"go_{i}"):
                st.session_state["render_pick"] = v.get("id")
                st.info("Open the 'Render' tab.")
            if c3.button("🗑 Delete", key=f"del_{i}"):
                scripts.pop(i)
                script.save_scripts(b["id"], scripts)
                st.rerun()


# ---- tab 5: render --------------------------------------------------------------------------

@st.fragment(run_every=2)
def job_progress(book_id: str) -> None:
    for s in jobs.recent(book_id, 3):
        if s["state"] in ("queued", "running"):
            st.progress(float(s.get("frac") or 0), text=f"🎬 {s.get('name')}: {s.get('msg')}")
        elif s["state"] == "error":
            st.error(f"'{s.get('name')}' failed: {s.get('error')}")
        elif s["state"] == "done" and time.time() - s.get("updated", 0) < 600:
            st.success(f"'{s.get('name')}' is ready - see the 'My videos' tab.")
            seen = st.session_state.setdefault("seen_jobs", set())
            if s["id"] not in seen:
                seen.add(s["id"])
                st.rerun(scope="app")


def tab_render(b: dict) -> None:
    st.subheader("🎥 Make the video")
    scripts = script.load_scripts(b["id"])
    job_progress(b["id"])
    if not scripts:
        st.info("Write a script first.")
        return
    ids = [v.get("id", str(i)) for i, v in enumerate(scripts)]
    pick = st.session_state.get("render_pick")
    sel = st.selectbox("Script", range(len(scripts)), ids.index(pick) if pick in ids else 0,
                       format_func=lambda i: f"{scripts[i].get('name')} ({scripts[i].get('created', '')})")
    v = scripts[sel]
    with st.expander("Preview scenes"):
        st.dataframe(scenes_frame(v)[["beat", "visual", "voiceover", "overlay", "page"]], hide_index=True,
                     width="stretch")

    g = GENRES[b["genre"]]
    c1, c2, c3 = st.columns(3)
    vlist = voice.voices()
    vdefault = voice.default_voice(b["genre"])
    vname = c1.selectbox(f"Narrator voice ({config.TTS_PROVIDER})", vlist,
                         vlist.index(vdefault) if vdefault in vlist else 0,
                         help="Default is chosen for the genre. Change the voice provider in Settings.")
    if c1.button("▶ Hear this voice (~$0.0003)"):
        wav = run_safely(voice.speak, f"This is the voice for {b['title']}.", vname, g["voice_instructions"],
                         bk.book_dir(b["id"]), b["genre"])
        if wav:
            c1.audio(str(wav))
    captions = c2.toggle("Word-by-word captions", True)
    page_sound = c2.toggle("Page-turn sound", True)
    tracks = sorted(p for p in config.MUSIC_DIR.glob("*") if p.suffix.lower() in MUSIC_EXT)
    music = c3.selectbox("Music", [None] + tracks, format_func=lambda p: "No music" if p is None else p.name)
    vol = c3.slider("Music volume", 0.05, 0.6, 0.25, 0.05)
    up = c3.file_uploader(f"Add music (royalty-free, {g['music_mood']} mood fits)", list(e[1:] for e in MUSIC_EXT))
    if up and c3.button("Save track"):
        (config.MUSIC_DIR / Path(up.name).name).write_bytes(up.getbuffer())
        st.rerun()

    est = render.estimate(b, v)
    left = budget.remaining()
    st.markdown(f"**Estimated cost:** up to {money(est['total'])} (voice {money(est['voice'])} · AI photos "
                f"{money(est['images'])} · AI video {money(est['ai_video'])}) · **Budget left:** {money(left)}  \n"
                "_Images and clips already made for this book are reused for free._")
    busy = any(s["state"] in ("queued", "running") for s in jobs.recent(b["id"], 3))
    if st.button("🎬 Render video", type="primary", disabled=busy or est["total"] > left):
        opts = {"voice_name": vname, "captions": captions, "music": str(music) if music else None,
                "music_volume": vol, "page_sound": page_sound}
        jobs.start(b["id"], v, opts)
        st.toast("Rendering started - this takes a few minutes on this PC.")
        time.sleep(1)
        st.rerun()
    if est["total"] > left:
        st.warning("This would go over your monthly budget. Reduce AI shots or turn on 'Free visuals only'.")


# ---- tab 6: videos + winners -----------------------------------------------------------------

def tab_videos(b: dict) -> None:
    st.subheader("📂 My videos")
    renders = render.list_renders(b["id"])
    if not renders:
        st.info("Rendered videos appear here.")
        return
    st.caption("Rule 5 - clone the winner: post several, log their views, then make variations of the best one "
               "that change ONE thing.")
    for r in renders:
        v = r["variant"]
        with st.container(border=True):
            c1, c2 = st.columns([1, 2])
            if Path(r["path"]).exists():
                c1.video(r["path"])
            with c2:
                st.markdown(f"**{v.get('name')}** · {r['seconds']}s · cost {money(r.get('cost', 0))} · {r['created']}")
                for w in r.get("warnings", []):
                    st.caption(f"⚠ {w}")
                st.code(f"{v.get('post_caption', '')}\n\n{' '.join(v.get('hashtags', []))}", language=None)
                if Path(r["path"]).exists():
                    st.download_button("⬇ Download MP4", Path(r["path"]).read_bytes(),
                                       file_name=f"{bk.slug(b['title'])}-{bk.slug(v.get('name', 'video'))}.mp4",
                                       mime="video/mp4", key=f"dl_{r['dir']}")
                k = r["dir"]
                cc = st.columns(3)
                views = cc[0].number_input("Views", 0, value=int(r.get("views", 0)), key=f"views_{k}")
                likes = cc[1].number_input("Likes", 0, value=int(r.get("likes", 0)), key=f"likes_{k}")
                winner = cc[2].checkbox("🏆 Winner", r.get("winner", False), key=f"win_{k}")
                if (views, likes, winner) != (r.get("views", 0), r.get("likes", 0), r.get("winner", False)):
                    render.update_render(k, views=views, likes=likes, winner=winner)
                if winner:
                    change = st.selectbox("Make 3 variations that change only…", [
                        "the hook (first line + first overlay)", "the footage / visuals",
                        "the pacing (faster cuts)", "the angle wording, same structure"], key=f"chg_{k}")
                    if st.button("🧬 Clone this winner", key=f"clone_{k}"):
                        with st.spinner("Writing variations..."):
                            out = run_safely(script.variations, b, v, change)
                            if out:
                                script.add_scripts(b["id"], out, f"variation of {v.get('name')}")
                                st.success(f"Added {len(out)} variations to the Scripts tab.")


# ---- main -------------------------------------------------------------------------------------

def password_gate() -> None:
    """On the web, only people with APP_PASSWORD can use the app (and spend the API credits)."""
    pw = os.getenv("APP_PASSWORD", "")
    if not pw:
        if WEB:
            st.error("Set APP_PASSWORD in the app's Secrets before using the web version - otherwise anyone with "
                     "the link could spend your API credits.")
            st.stop()
        return
    if st.session_state.get("authed"):
        return
    st.title("📚 Book Promo Studio")
    with st.form("login"):
        typed = st.text_input("Password", type="password")
        if st.form_submit_button("Enter", type="primary"):
            if hmac.compare_digest(typed.encode(), pw.encode()):
                st.session_state["authed"] = True
                st.rerun()
            st.error("Wrong password.")
    st.stop()


password_gate()
sidebar()
st.title("Book Promo Studio")
st.caption("Realistic, faceless promo videos for TikTok, Reels and Shorts: hook → feeling → proof from your pages → "
           "soft breadcrumb.")
b = pick_book()
if b:
    t = st.tabs(["1 · Book", "2 · Characters & pages", "3 · Viral format (optional)", "4 · Scripts", "5 · Render",
                 "6 · My videos"])
    with t[0]:
        tab_book(b)
    with t[1]:
        tab_characters_pages(b)
    with t[2]:
        tab_formats(b)
    with t[3]:
        tab_scripts(b)
    with t[4]:
        tab_render(b)
    with t[5]:
        tab_videos(b)

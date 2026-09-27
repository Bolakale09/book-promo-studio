"""Shared helpers: current book, navigation between steps, sidebar, settings + spending dialogs."""
import importlib
import os
import re
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from promo import book as bk, budget, config, jobs, render, script, storage
from promo.genres import GENRES

from . import theme as t

WEB = os.name != "nt"  # running on a Linux web server rather than the Windows PC
MUSIC_EXT = (".mp3", ".wav", ".m4a", ".aac", ".ogg")
PAGES: dict = {}       # key -> st.Page, filled in by app.py


# ---- small helpers -------------------------------------------------------------------------

def money(x: float) -> str:
    return f"${x:,.3f}" if x < 1 else f"${x:,.2f}"


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


def image_price() -> float:
    return budget.image_cost(config.IMAGE_MODEL, config.IMAGE_QUALITY)


def video_src(path: str | Path, download_name: str | None = None) -> str | None:
    """Local file if it's on this server, otherwise a private temporary link to the copy in cloud storage."""
    p = Path(path)
    if p.exists():
        return str(p)
    try:
        return storage.remote_url(p, download_name)
    except Exception:
        return None


def go(key: str, **state) -> None:
    st.session_state.update(state)
    st.switch_page(PAGES[key])


def next_step(key: str, text: str) -> None:
    st.divider()
    c1, c2 = st.columns([3, 1], vertical_alignment="center")
    c1.markdown(f'<span class="bps-muted">Next · {t.esc(text)}</span>', unsafe_allow_html=True)
    p = PAGES[key]
    c2.page_link(p, label=f"Continue to {p.title} →", width="stretch")


# ---- current book ----------------------------------------------------------------------------

def current_book() -> dict | None:
    books = bk.list_books()
    bid = st.session_state.get("book_id")
    if bid not in books:
        bid = next(iter(books), None)
    return bk.load(bid) if bid else None


def need_book() -> dict:
    b = current_book()
    if not b:
        t.header("Welcome", "Create your first book", "Everything starts with a book: its genre decides the angle, "
                                                        "hooks, voice and look of every video.")
        new_book_form("first")
        st.stop()
    return b


def new_book_form(key: str) -> None:
    with st.form(f"new_book_{key}", border=False):
        title = st.text_input("Book title", placeholder="e.g. Family Nurse Practitioner Pocket Guide")
        genre = st.pills("Genre", list(GENRES), default="fiction",
                         format_func=lambda g: f"{t.GENRE_ICON[g]} {GENRES[g]['label']}")
        if st.form_submit_button("Create book", type="primary", width="stretch") and title.strip():
            b = bk.new_book(title.strip())
            b["genre"] = genre or "fiction"
            bk.save(b)
            st.session_state["_goto_book"] = b["id"]  # applied before the book picker is drawn
            st.rerun()


def book_progress(b: dict) -> list[dict]:
    """The workflow checklist shown on the dashboard."""
    ms = bk.path(b, "manuscript")
    scripts = script.load_scripts(b["id"])
    renders = render.list_renders(b["id"])
    return [
        {"label": "Details & genre", "done": bool(b.get("blurb") or b.get("author")), "page": "book"},
        {"label": "Cover uploaded", "done": bool(bk.path(b, "cover")), "page": "book"},
        {"label": "Manuscript uploaded", "done": bool(ms and ms.exists()), "page": "book"},
        {"label": "AI read-through of the manuscript", "done": bool(b.get("digest")), "page": "book"},
        {"label": "Characters to show", "done": bool(b.get("characters")), "page": "characters", "optional": True},
        {"label": "Pages & lines to feature", "done": bool(b.get("featured")), "page": "pages", "optional": True},
        {"label": "Scripts written", "done": bool(scripts), "page": "scripts"},
        {"label": "First video rendered", "done": bool(renders), "page": "render"},
    ]


# ---- sidebar -----------------------------------------------------------------------------------

def sidebar() -> None:
    with st.sidebar:
        t.md('<div class="bps-brand"><div class="logo">📚</div><div>Book Promo Studio'
             '<small>faceless videos that sell books</small></div></div>')
        books = bk.list_books()
        if books:
            ids = list(books)
            if "_goto_book" in st.session_state:
                st.session_state["book_id"] = st.session_state.pop("_goto_book")
            if st.session_state.get("book_id") not in ids:
                st.session_state["book_id"] = ids[0]
            st.selectbox("Switch book", ids, key="book_id", format_func=lambda i: books[i]["title"])
            b = bk.load(st.session_state["book_id"])
            uri = t.img_uri(bk.path(b, "cover"), 120)
            cover = f'<img src="{uri}">' if uri else f'<div class="ph">{t.GENRE_ICON.get(b["genre"], "📘")}</div>'
            t.md(f'<div class="bps-side-book">{cover}<div><b>{t.esc(b["title"])}</b>'
                 f'{t.chip(t.GENRE_ICON.get(b["genre"], "") + " " + GENRES[b["genre"]]["label"], "gold")}</div></div>')
        with st.popover("➕ New book", width="stretch"):
            new_book_form("side")

        side_jobs()

        spent, cap = budget.spent_this_month(), config.MONTHLY_BUDGET_USD
        with st.container(border=True):
            t.md(f'<div class="bps-muted">Budget this month</div>'
                 f'<div style="font:700 1.35rem Fraunces,serif">{money(spent)} '
                 f'<span class="bps-muted" style="font:500 .85rem Inter">of {money(cap)}</span></div>'
                 + t.bar(spent / cap if cap else 1))
            if st.button("🧾 Spending log", width="stretch"):
                spending_dialog()
        if st.button("⚙️ Settings & API keys", width="stretch"):
            settings_dialog()
        if st.button("💾 Backup & storage", width="stretch"):
            storage_dialog()
        if storage.enabled():
            err = storage.state.get("last_error")
            when = (storage.state.get("last_sync") or (storage.state.get("restore") or {}).get("at") or "")[11:16]
            st.caption(f"⚠️ Cloud sync problem - open Backup & storage" if err else
                       f"☁️ Saved to cloud{' · ' + when if when else ''}")
        elif WEB:
            st.caption("⚠️ Not saved to cloud - data is lost when the app restarts. See Backup & storage.")

        missing = [k for k in ("OPENAI_API_KEY", "XAI_API_KEY") if not getattr(config, k)]
        if not config.XAI_API_KEY and not config.OPENAI_API_KEY:
            st.warning("Add an API key in ⚙️ Settings to start.")
        elif missing and len(missing) == 2:
            st.warning("Add an API key in Settings.")
        if not config.PEXELS_API_KEY:
            st.caption("💡 Add a free Pexels key in Settings for realistic stock footage at $0.")


@st.fragment(run_every=3)
def side_jobs() -> None:
    bid = st.session_state.get("book_id")
    if not bid:
        return
    for s in jobs.recent(bid, 2):
        if s["state"] in ("queued", "running"):
            st.progress(float(s.get("frac") or 0), text=f"🎬 {s.get('name')} · {int(100 * (s.get('frac') or 0))}%")
        elif s["state"] == "done":
            seen = st.session_state.setdefault("seen_jobs", set())
            if s["id"] not in seen:
                seen.add(s["id"])
                if time.time() - s.get("updated", 0) < 600:
                    st.toast(f"✅ '{s.get('name')}' is ready in Videos", icon="🎬")
                    st.rerun(scope="app")


# ---- dialogs -----------------------------------------------------------------------------------

def _save_env(values: dict) -> None:
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
    importlib.reload(config)


@st.dialog("Settings", width="large")
def settings_dialog() -> None:
    def key_input(col, label: str, attr: str) -> str:  # never send a saved key back to the browser
        saved = "saved ✓ - leave blank to keep" if getattr(config, attr) else "paste key"
        return col.text_input(label, type="password", placeholder=saved)

    st.markdown("**API keys**")
    c1, c2, c3 = st.columns(3)
    keys = {"XAI_API_KEY": key_input(c1, "xAI (Grok)", "XAI_API_KEY"),
            "OPENAI_API_KEY": key_input(c2, "OpenAI", "OPENAI_API_KEY"),
            "PEXELS_API_KEY": key_input(c3, "Pexels (free)", "PEXELS_API_KEY")}
    st.markdown("**Which AI does what**")
    prov = ["xai", "openai"]
    c1, c2 = st.columns(2)
    vals = {
        "LLM_PROVIDER": c1.segmented_control("Script writer", prov, default=config.LLM_PROVIDER, key="s_llm"),
        "IMAGE_PROVIDER": c2.segmented_control("AI photos", prov, default=config.IMAGE_PROVIDER, key="s_img"),
        "TTS_PROVIDER": c1.segmented_control("Narration voice", prov, default=config.TTS_PROVIDER, key="s_tts"),
        "VIDEO_PROVIDER": c2.segmented_control("AI video", prov, default=config.VIDEO_PROVIDER, key="s_vid"),
    }
    c1, c2 = st.columns(2)
    vals["IMAGE_QUALITY"] = c1.segmented_control("AI photo quality (OpenAI only)", ["low", "medium", "high"],
                                                 default=config.IMAGE_QUALITY, key="s_q")
    vals["MONTHLY_BUDGET_USD"] = str(c2.number_input("Monthly budget (USD)", 1.0, 500.0,
                                                     float(config.MONTHLY_BUDGET_USD), 1.0))
    st.caption(f"Now using: {config.LLM_MODEL} · {config.IMAGE_MODEL} · {config.TTS_MODEL} · {config.VIDEO_MODEL}")
    if WEB:
        st.caption("Web version: keys typed here last until the app restarts. Put them in the app's Secrets for good.")
    if st.button("Save settings", type="primary", width="stretch"):
        for k in ("LLM_MODEL", "IMAGE_MODEL", "VIDEO_MODEL", "TTS_MODEL"):  # let model defaults follow the provider
            os.environ.pop(k, None)
        vals = {k: v for k, v in vals.items() if v}
        vals.update({k: v for k, v in keys.items() if v.strip()})
        _save_env({k: v.strip() for k, v in vals.items()})
        st.rerun()


@st.dialog("Backup & storage", width="large")
def storage_dialog() -> None:
    s = storage.status()
    if s["enabled"]:
        st.success(f"☁️ Cloud storage is on - everything is saved to your Cloudflare R2 bucket **{s['bucket']}** "
                   "and comes back automatically when the app wakes up.")
        r = s.get("restore") or {}
        t.stats([("On this server", f"{s['local_files']} files", f"{s['local_mb']} MB"),
                 ("Last saved", (s.get("last_sync") or r.get("at") or "-")[11:19] or "-",
                  f"{s['uploaded']} uploaded · {s['deleted']} removed this session"),
                 ("Restored at start", str(r.get("downloaded", 0)), f"{r.get('videos_in_cloud', 0)} videos streamed")])
        if s.get("last_error"):
            st.error(f"Last sync failed: {s['last_error']}")
        tips = storage.diagnose()
        if tips:
            st.warning("Your R2 settings look off:  \n" + "  \n".join(f"• {x}" for x in tips))
        if st.button("🔌 Test connection", width="stretch"):
            with st.spinner("Connecting to R2..."):
                ok, msg = storage.test_connection()
            (st.success if ok else st.error)(msg + ("  \nNow close this and click **Try again** at the top of the "
                                                     "page to restore your library." if ok and
                                                     not storage.state.get("restored") else ""))
        c1, c2 = st.columns(2)
        if c1.button("🔄 Save to cloud now", type="primary", width="stretch"):
            with st.spinner("Uploading..."):
                res = run_safely(storage.sync_up)
            if res is not None:
                st.success(f"Up to date: {res['uploaded']} uploaded, {res['deleted']} removed.")
        if c2.button("📊 Check cloud usage", width="stretch"):
            u = run_safely(storage.cloud_usage)
            if u:
                st.info(f"{u['files']} files · {u['mb']} MB used of the 10 GB free tier "
                        f"({u['mb'] / 100:.1f}%)")
    else:
        st.warning("☁️ Cloud storage is off. " + ("On the web version your books, scripts and videos are deleted "
                                                  "whenever the app restarts." if WEB else
                                                  "Your data is saved on this PC only."))
        st.markdown("**Turn it on (Cloudflare R2, free up to 10 GB):**\n"
                    "1. Cloudflare dashboard → **R2** → **Create bucket** (e.g. `book-promo-studio`).\n"
                    "2. R2 → **Manage API tokens** → **Create API token** → permission **Object Read & Write**, "
                    "limited to that bucket.\n"
                    "3. Add these to the app's **Secrets** (web) or `.env` (PC), then restart the app:")
        st.code('R2_ACCOUNT_ID = "your account id"\nR2_ACCESS_KEY_ID = "..."\nR2_SECRET_ACCESS_KEY = "..."\n'
                'R2_BUCKET = "book-promo-studio"', language="toml")

    st.divider()
    b = current_book()
    st.markdown("**📦 Backup a book**" + (f" - _{t.esc(b['title'])}_" if b else ""))
    st.caption("One .zip with the book, manuscript, cover, characters, scripts, AI shots and (optionally) videos. "
               "Keep it on your PC as an extra safety net - it works even without cloud storage.")
    if b:
        c1, c2 = st.columns([2, 3], vertical_alignment="center")
        include = c1.toggle("Include videos", True)
        if c2.button("Prepare backup", width="stretch"):
            with st.spinner("Packing..."):
                data = run_safely(storage.backup_zip, b["id"], include)
            if data:
                st.session_state["_backup"] = (b["id"], data)
        ready = st.session_state.get("_backup")
        if ready and ready[0] == b["id"]:
            st.download_button(f"⬇ Download backup ({len(ready[1]) / 1e6:.1f} MB)", ready[1], type="primary",
                               file_name=f"{b['id']}-backup-{time.strftime('%Y-%m-%d')}.zip",
                               mime="application/zip", width="stretch")

    st.markdown("**♻️ Restore a backup**")
    up = st.file_uploader("Backup .zip made by this app", ["zip"], key="restore_zip")
    if up and st.button("Restore this backup", width="stretch"):
        with st.spinner("Restoring..."):
            bid = run_safely(storage.restore_zip, up.getvalue())
        if bid:
            st.session_state["_goto_book"] = bid
            st.session_state.pop("_backup", None)
            storage.sync_soon()
            st.rerun()


@st.dialog("Spending", width="large")
def spending_dialog() -> None:
    spent, cap = budget.spent_this_month(), config.MONTHLY_BUDGET_USD
    t.stats([("This month", money(spent)), ("Left", money(max(0, cap - spent))), ("Budget", money(cap))])
    rows = budget.recent(200)
    if not rows:
        st.caption("Nothing spent yet.")
        return
    df = pd.DataFrame(rows)
    month = df[df["month"] == df["month"].max()]
    st.bar_chart(month.groupby("service")["cost"].sum(), horizontal=True, height=180)
    st.dataframe(df[["ts", "service", "model", "cost", "note"]].head(60), hide_index=True, width="stretch")


# ---- script table helpers -------------------------------------------------------------------------

SCENE_COLS = ["beat", "visual", "voiceover", "overlay", "page", "highlight", "flips", "character", "prompt",
              "stock_query", "seconds"]


def scenes_frame(v: dict) -> pd.DataFrame:
    return pd.DataFrame([{c: s.get(c) for c in SCENE_COLS} for s in v.get("scenes", [])], columns=SCENE_COLS)


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

"""Viral finder: search a keyword for viral book videos, copy a video's style, and mine ideas."""
import streamlit as st

from promo import analyze, discover, jobs

from . import theme as t
from .common import _save_env, go, need_book, start_task, task_panel

KINDS = {"discover", "ideas", "study"}
PLATFORM_ICON = {"TikTok": "🎵", "Instagram": "📸", "YouTube": "▶️", "Other": "🎬"}


def _n(x) -> str:
    if x is None:
        return "?"
    for size, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if x >= size:
            return f"{x / size:.1f}".rstrip("0").rstrip(".") + suf
    return str(int(x))


def _busy(b: dict) -> bool:
    return bool(jobs.active(b["id"], KINDS))


def _search_box(b: dict, found: dict) -> None:
    src = discover.sources()
    with st.container(border=True):
        ideas_words = discover.suggest_keywords(b)
        pick = st.pills("Try", ideas_words, default=None, key="disc_pick", label_visibility="collapsed")
        if pick and st.session_state.get("disc_pick_used") != pick:
            st.session_state["disc_kw"] = pick
            st.session_state["disc_pick_used"] = pick
        st.session_state.setdefault("disc_kw", found.get("keyword") or ideas_words[0])
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        kw = c1.text_input("Book title, genre or trope", key="disc_kw",
                           help="A title, a trope ('enemies to lovers'), or a topic ('nurse practitioner study guide').")
        with_ideas = st.checkbox("Also write the idea board (about $0.01)", value=True, key="disc_ideas")
        if c2.button("🔎 Find viral videos", type="primary", width="stretch", disabled=not kw.strip() or _busy(b)):
            start_task("discover", b["id"], kw.strip(), {"keyword": kw.strip(), "ideas": with_ideas})
        t.chips([(("✓ " if s["ready"] else "✗ ") + s["label"], "gold" if s["ready"] else "") for s in src.values()])
    with st.expander("Get real TikTok / Instagram view counts (optional)"):
        st.markdown("TikTok and Instagram don't offer a free public search, so the app can't list their videos on its "
                    "own. Grok's search finds public links; **Apify** returns real view counts. Both are optional - "
                    "YouTube Shorts and pasting links always work.")
        tok = st.text_input("Apify token", type="password", value="",
                            placeholder="Saved" if src["apify"]["ready"] else "apify_api_...")
        if st.button("Save token", disabled=not tok.strip()):
            _save_env({"APIFY_TOKEN": tok.strip()})
            st.rerun()
        st.caption("Instagram downloads often need a login. Put an exported cookies.txt path in COOKIES_FILE (.env), "
                   "or download the video yourself and upload it on the Format page.")


def _card(b: dict, v: dict, i: int) -> None:
    url = v["url"]
    done = discover.studied(url)
    with st.container(border=True):
        if v.get("thumbnail"):
            try:
                st.image(v["thumbnail"], width="stretch")
            except Exception:
                pass
        st.markdown(f'<div class="bps-card-title">{t.esc((v.get("title") or "(no title)")[:90])}</div>',
                    unsafe_allow_html=True)
        chips = [(f"{PLATFORM_ICON.get(v['platform'], '🎬')} {v['platform']}", "blue"),
                 (f"👁 {_n(v.get('views'))}", "gold" if v.get("views") else "")]
        if v.get("likes") is not None:
            chips.append((f"♥ {_n(v['likes'])}", ""))
        if v.get("seconds"):
            chips.append((f"{v['seconds']}s", ""))
        t.chips(chips)
        if v.get("author"):
            st.caption(f"by {v['author']}")
        if v.get("unverified"):
            st.caption("Link not verified - open it to check.")
        st.link_button("Open ↗", url, width="stretch")
        if done:
            if st.button("✅ Use this style for scripts", key=f"vf_use_{i}", type="primary", width="stretch"):
                go("scripts", bp_choice=discover.bp_id_for(url))
        elif st.button("🔁 Copy this style", key=f"vf_copy_{i}", type="primary", width="stretch", disabled=_busy(b),
                       help="Downloads it and studies its structure - hook, pacing, overlays, ending. Never its words."):
            start_task("study", b["id"], (v.get("title") or url)[:40],
                       {"url": url, "stats": {k: v.get(k) for k in ("views", "likes", "shares", "platform")}},
                       note="Studying the video - this takes a few minutes on a slow PC")


def _videos_tab(b: dict, found: dict) -> None:
    with st.form("disc_paste", border=False, clear_on_submit=True):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        link = c1.text_input("Found one yourself? Paste its link", placeholder="https://www.tiktok.com/@.../video/...")
        if c2.form_submit_button("Add", width="stretch") and link.strip():
            try:
                item = discover.add_link(link.strip())
                found.setdefault("videos", [])
                found["videos"] = [item] + [v for v in found["videos"] if v["url"] != item["url"]]
                discover.save(b["id"], found)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    vids = found.get("videos") or []
    for n in found.get("notes", []):
        st.caption("• " + n)
    if not vids:
        t.empty("🔥", "Search a keyword above, or paste a link you found."
                if not found else "No videos found for that keyword - try a broader one, or use the links below.")
        return
    st.markdown(f"#### {len(vids)} videos for “{t.esc(found.get('keyword', ''))}” · best first")
    for row in range(0, len(vids), 3):
        cols = st.columns(3)
        for j, v in enumerate(vids[row:row + 3]):
            with cols[j]:
                _card(b, v, row + j)


def _ideas_tab(b: dict, found: dict) -> None:
    ideas = found.get("ideas")
    kw = found.get("keyword") or st.session_state.get("disc_kw", "")
    if st.button("💡 " + ("Refresh ideas" if ideas else "Write the idea board"), disabled=_busy(b) or not kw.strip(),
                 help="Uses your book plus the videos found. About $0.01."):
        start_task("ideas", b["id"], kw[:40], {"keyword": kw})
    if not ideas:
        t.empty("💡", "The idea board turns what's working into hooks, angles, video ideas, hashtags and comparable books.")
        return
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🪝 Hook bank")
        hooks_ = ideas.get("hooks") or []
        for h in hooks_:
            st.markdown(f"**{t.esc(h.get('text', ''))}**  \n"
                        f"<span class='bps-muted'>{t.esc(h.get('type', ''))} · {t.esc(h.get('why', ''))}</span>",
                        unsafe_allow_html=True)
        chosen = st.multiselect("Score these in the Hook lab", [h.get("text", "") for h in hooks_], key="disc_hooks")
        if st.button("🧪 Test the chosen hooks", disabled=not chosen or _busy(b)):
            start_task("hooks", b["id"], "Hook test", {"n": 0, "custom": chosen})
        st.markdown("#### 🎯 Angles")
        for a in ideas.get("angles") or []:
            st.markdown(f"**{t.esc(a.get('angle', ''))}**  \n“{t.esc(a.get('first_line', ''))}”  \n"
                        f"<span class='bps-muted'>{t.esc(a.get('why', ''))}</span>", unsafe_allow_html=True)
    with c2:
        st.markdown("#### 🎬 Video ideas")
        for v in ideas.get("video_ideas") or []:
            st.markdown(f"**{t.esc(v.get('title', ''))}** · <span class='bps-muted'>{t.esc(v.get('format', ''))}</span>  \n"
                        f"{t.esc(v.get('beats', ''))}", unsafe_allow_html=True)
        if ideas.get("trends"):
            st.markdown("#### 📈 What the found videos share")
            for x in ideas["trends"]:
                st.markdown(f"- {x}")
        st.markdown("#### 📚 Comparable books")
        st.caption("Readers of these are your audience - double-check each one exists before you mention it.")
        for c in ideas.get("comparables") or []:
            st.markdown(f"**{t.esc(c.get('title', ''))}** {t.esc(c.get('author', ''))}  \n"
                        f"<span class='bps-muted'>{t.esc(c.get('why', ''))}</span>", unsafe_allow_html=True)
    st.markdown("#### #️⃣ Hashtags")
    st.code(" ".join(ideas.get("hashtags") or []), language=None)
    st.markdown("#### ✏️ Captions")
    for c in ideas.get("captions") or []:
        st.code(c, language=None, wrap_lines=True)


def _links_tab(found: dict) -> None:
    kw = found.get("keyword") or st.session_state.get("disc_kw", "")
    st.caption("Search yourself in the apps, then paste any video you like into the box on the first tab.")
    cols = st.columns(4)
    for col, (label, url) in zip(cols, discover.search_links(kw or "booktok")):
        if url:
            col.link_button(label + " ↗", url, width="stretch")


def viral_page() -> None:
    b = need_book()
    t.header("Viral finder", "Find what's going viral, then copy its style",
             "Type your book title or a trope. The app finds popular book videos; one click studies a video's "
             "structure (hook, pacing, overlays, ending - never its words) and uses it for your scripts.")
    found = discover.load(b["id"])
    task_panel(b["id"], KINDS)
    _search_box(b, found)
    tab1, tab2, tab3 = st.tabs(["🔥 Viral videos", "💡 Idea board", "🔗 Search in the apps"])
    with tab1:
        _videos_tab(b, found)
    with tab2:
        _ideas_tab(b, found)
    with tab3:
        _links_tab(found)
    bps = analyze.list_blueprints()
    if bps:
        st.caption(f"{len(bps)} saved format(s) - manage them on the Format page.")

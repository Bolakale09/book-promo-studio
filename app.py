"""Book Promo Studio - turn a book into realistic, faceless TikTok / Reels / Shorts videos.

Run with:  run.bat   (or: .venv\\Scripts\\streamlit run app.py)
"""
import hmac
import os

import streamlit as st

from promo import storage
from ui import common, theme
from ui.grow_pages import brand_page, calendar_page, results_page
from ui.create_pages import render_page, scripts_page, videos_page
from ui.manage_pages import backup_page
from ui.setup_pages import book_page, characters_page, formats_page, home, pages_page

st.set_page_config(page_title="Book Promo Studio", page_icon="📚", layout="wide")
theme.inject()


def password_gate() -> None:
    """On the web, only people with APP_PASSWORD can use the app (and spend the API credits)."""
    pw = os.getenv("APP_PASSWORD", "")
    if not pw:
        if common.WEB:
            st.error("Set APP_PASSWORD in the app's Secrets before using the web version - otherwise anyone with "
                     "the link could spend your API credits.")
            st.stop()
        return
    if st.session_state.get("authed"):
        return
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.write("")
        theme.md('<div class="bps-brand" style="justify-content:center;font-size:1.5rem;margin:3rem 0 1.2rem">'
                 '<div class="logo">📚</div><div>Book Promo Studio<small>faceless videos that sell books</small>'
                 '</div></div>')
        with st.form("login"):
            typed = st.text_input("Password", type="password")
            if st.form_submit_button("Enter", type="primary", width="stretch"):
                if hmac.compare_digest(typed.encode(), pw.encode()):
                    st.session_state["authed"] = True
                    st.rerun()
                st.error("Wrong password.")
    st.stop()


@st.cache_resource(show_spinner=False)
def restore_library() -> dict:
    """Once per server start: bring back books, scripts, AI shots and the spending log from Cloudflare R2."""
    try:
        return {"ok": True, **storage.restore()}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


password_gate()
if storage.enabled():
    with st.spinner("Restoring your library from cloud storage..."):
        boot = restore_library()
    if not boot["ok"]:
        hint = storage.explain(boot["error"])
        tips = storage.diagnose()
        st.error(f"Couldn't reach your cloud storage, so changes are NOT being saved to the cloud right now.  \n"
                 f"`{boot['error'][:200]}`" + (f"  \n**Likely cause:** {hint}" if hint else "")
                 + ("  \n**Check your R2 settings in Secrets:**  \n" + "  \n".join(f"• {x}" for x in tips)
                    if tips else ""))
        if st.button("Try again"):
            restore_library.clear()
            st.rerun()

common.PAGES.update({
    "home": st.Page(home, title="Studio", icon="🏠", url_path="studio", default=True),
    "book": st.Page(book_page, title="1 Book", icon="📘", url_path="book"),
    "characters": st.Page(characters_page, title="2 Characters", icon="🎭", url_path="characters"),
    "pages": st.Page(pages_page, title="3 Pages", icon="📖", url_path="pages"),
    "formats": st.Page(formats_page, title="4 Format", icon="🔁", url_path="format"),
    "scripts": st.Page(scripts_page, title="5 Scripts", icon="✍️", url_path="scripts"),
    "render": st.Page(render_page, title="6 Render", icon="🎬", url_path="render"),
    "videos": st.Page(videos_page, title="7 Videos", icon="📂", url_path="videos"),
    "brand": st.Page(brand_page, title="Brand kit", icon="🎨", url_path="brand"),
    "calendar": st.Page(calendar_page, title="Calendar", icon="📅", url_path="calendar"),
    "results": st.Page(results_page, title="Results", icon="📈", url_path="results"),
    "backup": st.Page(backup_page, title="Backup & storage", icon="💾", url_path="backup", visibility="hidden"),
})
P = common.PAGES
nav = st.navigation({
    "": [P["home"]],
    "Set up": [P["book"], P["characters"], P["pages"], P["formats"], P["brand"]],
    "Make": [P["scripts"], P["render"]],
    "Publish": [P["videos"], P["calendar"], P["results"]],
    "Other": [P["backup"]],
}, position="top")
common.sidebar()
try:
    nav.run()
finally:
    storage.sync_soon()  # upload whatever this action changed, in the background

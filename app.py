"""Book Promo Studio - turn a book into realistic, faceless TikTok / Reels / Shorts videos.

Run with:  run.bat   (or: .venv\\Scripts\\streamlit run app.py)
"""
import hmac
import os

import streamlit as st

from ui import common, theme
from ui.create_pages import render_page, scripts_page, videos_page
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


password_gate()

common.PAGES.update({
    "home": st.Page(home, title="Studio", icon="🏠", url_path="studio", default=True),
    "book": st.Page(book_page, title="1 Book", icon="📘", url_path="book"),
    "characters": st.Page(characters_page, title="2 Characters", icon="🎭", url_path="characters"),
    "pages": st.Page(pages_page, title="3 Pages", icon="📖", url_path="pages"),
    "formats": st.Page(formats_page, title="4 Format", icon="🔁", url_path="format"),
    "scripts": st.Page(scripts_page, title="5 Scripts", icon="✍️", url_path="scripts"),
    "render": st.Page(render_page, title="6 Render", icon="🎬", url_path="render"),
    "videos": st.Page(videos_page, title="7 Videos", icon="📂", url_path="videos"),
})
nav = st.navigation(list(common.PAGES.values()), position="top")
common.sidebar()
nav.run()

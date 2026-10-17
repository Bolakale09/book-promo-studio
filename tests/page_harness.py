import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import streamlit as st

from ui import common, theme
from ui.create_pages import render_page, scripts_page, videos_page
from ui.discover_pages import viral_page
from ui.grow_pages import brand_page, calendar_page, results_page
from ui.setup_pages import characters_page, formats_page, home, pages_page

theme.inject()
target = os.environ.get("PAGE", "home")
fns = dict(home=home, scripts=scripts_page, render=render_page, videos=videos_page, brand=brand_page,
           calendar=calendar_page, results=results_page, viral=viral_page, formats=formats_page,
           characters=characters_page, pages=pages_page)
common.PAGES.update({k: st.Page(f, title=k, url_path=k, default=(k == target)) for k, f in fns.items()})
st.navigation(list(common.PAGES.values()), position="top").run()

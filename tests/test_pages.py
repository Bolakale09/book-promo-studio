"""Slow smoke tests (run with: pytest -m slow): every page must load for a real-looking book without an exception."""
from pathlib import Path

import pytest

HARNESS = Path(__file__).parent / "page_harness.py"
PAGES = ["home", "scripts", "render", "videos", "brand", "calendar", "results", "viral", "formats", "characters",
         "pages"]
pytestmark = pytest.mark.slow


@pytest.mark.parametrize("page", PAGES)
def test_page_loads(page, data, book, make_render, monkeypatch):
    from streamlit.testing.v1 import AppTest
    make_render(book["id"], 1, views=120)
    monkeypatch.setenv("PAGE", page)
    at = AppTest.from_file(str(HARNESS), default_timeout=300)
    at.session_state["book_id"] = book["id"]
    at.run()
    assert not at.exception, [e.value for e in at.exception]

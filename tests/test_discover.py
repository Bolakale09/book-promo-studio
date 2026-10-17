import pytest

from promo import discover


def vid(url, views=None, platform="YouTube", **kw):
    return {"url": url, "platform": platform, "title": kw.pop("title", ""), "author": "", "views": views,
            "likes": None, "shares": None, "seconds": None, "thumbnail": "", "source": "t", **kw}


@pytest.mark.parametrize("text,want", [("1.2M", 1_200_000), ("~350K views", 350_000), ("2,500", 2500),
                                       ("1.5b", 1_500_000_000), ("unknown", None), ("", None), (None, None)])
def test_parse_views(text, want):
    assert discover._parse_views(text) == want


@pytest.mark.parametrize("url,want", [("https://www.tiktok.com/@a/video/1", "TikTok"),
                                      ("https://www.instagram.com/reel/abc/", "Instagram"),
                                      ("https://youtu.be/xyz", "YouTube"), ("https://example.com", "Other")])
def test_platform_of(url, want):
    assert discover.platform_of(url) == want


def test_add_link_extracts_and_rejects(monkeypatch):
    monkeypatch.setattr(discover, "enrich", lambda item, timeout=8: item)
    item = discover.add_link("look https://www.tiktok.com/@z/video/99?lang=en, nice")
    assert item["url"] == "https://www.tiktok.com/@z/video/99?lang=en" and item["platform"] == "TikTok"
    with pytest.raises(ValueError):
        discover.add_link("https://example.com/video")


def test_suggest_keywords_dedupes_and_starts_with_title():
    kws = discover.suggest_keywords({"title": "Booktok", "genre": "fiction",
                                     "digest": {"tropes_or_hooks": ["slow burn"]}})
    assert kws[0] == "Booktok" and len(kws) == len({k.lower() for k in kws}) and "slow burn books" in kws


def test_search_links_encode_keyword():
    links = dict(discover.search_links("enemies to lovers"))
    assert "enemies%20to%20lovers" in links["TikTok search"] and links["TikTok hashtag"].endswith("/enemiestolovers")


def test_search_merges_duplicates_drops_dead_and_sorts(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "")
    monkeypatch.setattr(discover.config, "XAI_API_KEY", "x")
    monkeypatch.setattr(discover, "from_grok", lambda kw, limit=12: [
        vid("https://www.tiktok.com/@a/video/1", platform="TikTok"),
        vid("https://www.tiktok.com/@a/video/2", 5_000_000, "TikTok"),
        vid("https://www.youtube.com/shorts/a2", 1)])
    monkeypatch.setattr(discover, "from_youtube", lambda kw, limit=15: [
        vid("https://www.youtube.com/shorts/a1", 1000), vid("https://www.youtube.com/shorts/a2", 900_000)])
    monkeypatch.setattr(discover, "enrich", lambda i, timeout=8: None if i["url"].endswith("/video/1") else i)
    rows, notes = discover.search("kw")
    assert [r["views"] for r in rows] == [5_000_000, 900_000, 1000]
    assert any("Apify" in n for n in notes)


def test_search_survives_a_failing_source(monkeypatch):
    def boom(kw, limit=15):
        raise RuntimeError("boom")
    monkeypatch.setenv("APIFY_TOKEN", "")
    monkeypatch.setattr(discover.config, "XAI_API_KEY", "")
    monkeypatch.setattr(discover, "from_youtube", boom)
    rows, notes = discover.search("kw")
    assert rows == [] and any("failed" in n for n in notes)


def test_search_rejects_empty_keyword():
    with pytest.raises(ValueError):
        discover.search("   ")


def test_run_search_saves_videos_even_if_ideas_fail(data, book, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(discover, "search",
                        lambda kw, progress=None: ([vid("https://www.youtube.com/shorts/a", 5)], ["n"]))
    monkeypatch.setattr(discover, "make_ideas", boom)
    out = discover.run_search(book, "kw", ideas=True)
    saved = discover.load(book["id"])
    assert saved["videos"][0]["views"] == 5 and out["ideas"] is None
    assert any("Idea board failed" in n for n in saved["notes"])


def test_studied_follows_blueprint_file(data):
    from promo import config
    url = "https://www.tiktok.com/@a/video/2"
    assert not discover.studied(url)
    (config.BLUEPRINTS_DIR / f"{discover.bp_id_for(url)}.json").write_text("{}")
    assert discover.studied(url)

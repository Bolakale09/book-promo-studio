from ui import theme


def test_sparkline_needs_two_points_and_is_valid_svg():
    assert theme.sparkline([5]) == ""
    svg = theme.sparkline([1, 4, 2, 9])
    assert svg.startswith("<svg") and svg.endswith("</svg>") and svg.count("<path") == 3


def test_sparkline_flat_series_does_not_divide_by_zero():
    assert "<svg" in theme.sparkline([3, 3, 3])


def test_user_text_is_escaped(monkeypatch):
    out = []
    monkeypatch.setattr(theme.st, "markdown", lambda html, **k: out.append(html))
    theme.momentum(("<b>x</b>", "1", "<script>alert(1)</script>", ""), [("<i>", "2", "s")])
    theme.metric("<img>", "1", "<svg onload=1>", [1, 2])
    html = "".join(out)
    assert "<script>" not in html and "<b>x</b>" not in html and "<img>" not in html


def test_android_app_is_detected_from_user_agent(monkeypatch):
    from types import SimpleNamespace
    out = []
    monkeypatch.setattr(theme.st, "markdown", lambda html, **k: out.append(html))
    monkeypatch.setattr(theme.st, "context", SimpleNamespace(headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14)"}))
    assert not theme.in_app()
    theme.inject()
    monkeypatch.setattr(theme.st, "context", SimpleNamespace(headers={"User-Agent": "Mozilla/5.0 BookPromoStudioApp/1"}))
    assert theme.in_app()
    theme.inject()
    assert theme.APP_CSS not in out[0] and theme.APP_CSS in out[1]


def test_in_app_is_false_outside_a_request(monkeypatch):
    monkeypatch.setattr(theme.st, "context", None)  # .headers raises -> treated as a normal browser
    assert theme.in_app() is False


def test_timeline_has_one_cell_per_scene():
    html = theme.timeline([{"visual": "stock", "voiceover": "one two three four five six seven"},
                           {"visual": "cover", "seconds": 3}])
    assert html.count('class="sc') == 2 and "--w:" in html

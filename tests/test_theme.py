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


def test_timeline_has_one_cell_per_scene():
    html = theme.timeline([{"visual": "stock", "voiceover": "one two three four five six seven"},
                           {"visual": "cover", "seconds": 3}])
    assert html.count('class="sc') == 2 and "--w:" in html

from PIL import Image, ImageChops

from promo import script, ugc
from promo.genres import default_blueprint

SCENE = {"visual": "stock", "stock_query": "reading", "voiceover": "ok so", "overlay": "hi"}


def test_phone_look_changes_picture_but_keeps_size():
    src = Image.new("RGB", (270, 480), (200, 190, 170))
    out = ugc.PhoneLook(270, 480, seed=1, fps=30)(src.copy(), 0.4, scene=1)
    assert out.size == src.size and ImageChops.difference(out, src).getbbox() is not None


def test_phone_look_is_deterministic_per_seed():
    src = Image.new("RGB", (270, 480), (120, 90, 60))
    a = ugc.PhoneLook(270, 480, seed=3)(src.copy(), 1.0, 0)
    b = ugc.PhoneLook(270, 480, seed=3)(src.copy(), 1.0, 0)
    assert ImageChops.difference(a, b).getbbox() is None


def test_ugc_style_reaches_prompt_and_variants(book, monkeypatch):
    seen = {}

    def fake(system, user, **k):
        seen["user"] = user
        return {"variants": [{"name": "x", "scenes": [dict(SCENE)]}]}
    monkeypatch.setattr(script.llm, "chat_json", fake)
    v = script.generate(book, default_blueprint("fiction"), n=1, style="ugc")
    assert v[0]["style"] == "ugc" and "UGC STYLE" in seen["user"]
    v = script.generate(book, default_blueprint("fiction"), n=1)
    assert "style" not in v[0] and "UGC STYLE" not in seen["user"]


def test_scripts_always_end_on_the_cover(book, monkeypatch):
    monkeypatch.setattr(script.llm, "chat_json", lambda *a, **k: {"variants": [{"name": "x", "scenes": [dict(SCENE)]}]})
    v = script.generate(book, default_blueprint("fiction"), n=1)
    assert v[0]["scenes"][-1]["visual"] == "cover"

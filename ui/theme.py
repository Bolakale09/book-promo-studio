"""Look and feel: CSS plus small HTML building blocks (page headers, chips, stat cards, scene timeline)."""
import base64
import html
from pathlib import Path

import streamlit as st

GENRE_ICON = {"fiction": "📖", "self-help": "🌱", "poetry": "🪶", "gift": "🎁", "medical": "🩺",
              "engineering": "⚙️", "children": "🧸"}
VISUAL_ICON = {"page": "📄", "flip": "📚", "cover": "📕", "stock": "🎞️", "broll": "🎥", "character": "🧑",
               "ai_image": "🖼️", "ai_video": "🎬"}
VISUAL_LABEL = {"page": "Page", "flip": "Page flip", "cover": "Cover", "stock": "Stock", "broll": "Your clip",
                "character": "Character", "ai_image": "AI photo", "ai_video": "AI video"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Inter:wght@400;500;600;700&display=swap');
:root { --gold:#FF5A36; --gold2:#FF9A7A; --card:#14141F; --card2:#1C1C2A; --line:#2A2D38; --muted:#9C978E;
        --text:#F5F2EA; }
.block-container { padding-top: 4.6rem; padding-bottom: 5rem; max-width: 1180px; position: relative; z-index: 1; }
[data-testid="stBaseButton-primary"], button[kind="primary"] { color:#0B0B14 !important; font-weight:650; }
[data-testid="stBaseButton-primary"] p { color:#0B0B14 !important; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .7rem; }

/* page header */
.bps-head { margin: .1rem 0 1.3rem; }
.bps-eyebrow { font: 650 .72rem/1 Inter, sans-serif; letter-spacing: .16em; text-transform: uppercase;
               color: var(--gold); margin-bottom: .5rem; }
.bps-title { font-family: Fraunces, Georgia, serif; font-size: 2.15rem; font-weight: 700; line-height: 1.08;
             margin: 0; color: var(--text); }
.bps-sub { color: var(--muted); margin-top: .45rem; font-size: .98rem; max-width: 70ch; }

/* hero */
.bps-hero { display:flex; gap:1.5rem; align-items:center; padding:1.5rem 1.6rem; border-radius:20px;
  background: radial-gradient(120% 160% at 0% 0%, rgba(255,90,54,.20), transparent 55%),
              linear-gradient(135deg,#1C1F2B,#111219); border:1px solid var(--line); margin-bottom: 1.2rem; }
.bps-hero img, .bps-cover-ph { width: 96px; min-width: 96px; border-radius: 6px;
  box-shadow: 0 14px 34px rgba(0,0,0,.55), 0 0 0 1px rgba(255,255,255,.06); }
.bps-cover-ph { height: 144px; display:flex; align-items:center; justify-content:center; font-size:2.2rem;
  background: linear-gradient(160deg,#2b3350,#161a2a); }
.bps-hero h2 { font-family: Fraunces, Georgia, serif; font-size: 1.9rem; margin: .1rem 0 .35rem; line-height:1.1; }
.bps-hero .meta { color: var(--muted); font-size: .92rem; margin-bottom: .6rem; }

/* chips */
.bps-chip { display:inline-flex; align-items:center; gap:.3rem; padding:.2rem .62rem; border-radius:999px;
  font-size:.76rem; font-weight:600; background: rgba(255,255,255,.05); border:1px solid var(--line);
  color: var(--text); margin: 0 .3rem .3rem 0; white-space: nowrap; }
.bps-chip.gold { background: rgba(255,90,54,.13); border-color: rgba(255,90,54,.45); color: var(--gold2); }
.bps-chip.green { background: rgba(76,175,120,.14); border-color: rgba(76,175,120,.45); color:#8FE0B0; }
.bps-chip.red { background: rgba(230,90,80,.14); border-color: rgba(230,90,80,.45); color:#F4A49B; }
.bps-chip.blue { background: rgba(110,160,240,.14); border-color: rgba(110,160,240,.45); color:#A9C6F5; }

/* progress + checklist */
.bps-bar { height: 8px; background: rgba(255,255,255,.07); border-radius: 99px; overflow: hidden; margin:.4rem 0 .2rem; }
.bps-bar > div { height: 100%; background: linear-gradient(90deg,#FF7A2F,#FF5A36,#FF9A7A); border-radius: 99px; }
.bps-check { display:flex; align-items:center; gap:.75rem; padding:.62rem .1rem; border-bottom:1px dashed var(--line); }
.bps-check:last-child { border-bottom: 0; }
.bps-check .dot { width:24px; height:24px; min-width:24px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-size:.74rem; font-weight:700; border:1.5px solid var(--line); color: var(--muted); }
.bps-check.done .dot { background:#2F8A57; border-color:#2F8A57; color:#fff; }
.bps-check.next .dot { border-color: var(--gold); color: var(--gold); box-shadow: 0 0 0 4px rgba(255,90,54,.16); }
.bps-check .lbl { flex:1; font-size:.95rem; }
.bps-check.done .lbl { color: var(--muted); }
.bps-check .opt { color: var(--muted); font-size: .76rem; }

/* stat cards */
.bps-stat { padding: 1rem 1.15rem; border-radius: 14px; background: var(--card); border: 1px solid var(--line); height:100%; }
.bps-stat .l { color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .1em; font-weight:600; }
.bps-stat .v { font: 700 1.7rem/1.15 Fraunces, Georgia, serif; margin-top: .25rem; color: var(--text); }
.bps-stat .s { color: var(--muted); font-size: .8rem; margin-top: .15rem; }

/* scene timeline */
.bps-tl { display:flex; gap:4px; width:100%; margin:.55rem 0 .35rem; }
.bps-tl .sc { flex-grow: var(--w); flex-basis: 0; min-width: 38px; height: 54px; border-radius: 9px;
  padding: 6px 8px; font-size: .68rem; line-height: 1.2; overflow: hidden; color:#15130F; font-weight: 650; }
.bps-tl .sc .ic { font-size: 1rem; display:block; margin-bottom: 2px; }
.bps-tl .sc .bt { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display:block; opacity:.85; }
.t-page { background:#EADFC6; } .t-flip { background:#D9C8A0; } .t-cover { background:#FF5A36; }
.t-stock { background:#86BCE8; } .t-broll { background:#9DD6C4; } .t-character { background:#EDA7C4; }
.t-ai_image { background:#BDA8F2; } .t-ai_video { background:#F29272; }
.bps-legend { display:flex; flex-wrap:wrap; gap:.8rem; font-size:.76rem; color:var(--muted); margin:.2rem 0 .6rem; }
.bps-legend i { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:.3rem; vertical-align:-1px; }

/* misc */
.bps-card-title { font-family: Fraunces, Georgia, serif; font-size: 1.22rem; font-weight: 700; margin: 0 0 .15rem; }
.bps-muted { color: var(--muted); font-size: .88rem; }
.bps-quote { font-family: Fraunces, Georgia, serif; font-size: 1.02rem; line-height: 1.45; border-left: 3px solid var(--gold);
  padding: .1rem 0 .1rem .8rem; margin: .3rem 0 .5rem; }
.bps-avatar { width:100%; aspect-ratio: 3/4; border-radius: 12px; display:flex; align-items:center; justify-content:center;
  font: 700 2.6rem Fraunces, Georgia, serif; color: var(--gold2);
  background: radial-gradient(90% 90% at 30% 20%, rgba(255,90,54,.25), transparent 60%), linear-gradient(160deg,#2a2f45,#161923); }
.bps-brand { display:flex; align-items:center; gap:.65rem; font-family: Fraunces, Georgia, serif; font-weight:700;
  font-size:1.2rem; margin: -.4rem 0 .9rem; line-height: 1.15; }
.bps-brand .logo { width:36px; height:36px; border-radius:10px; display:flex; align-items:center; justify-content:center;
  background: linear-gradient(135deg,#FF5A36,#FF3D6E); font-size:1.15rem; box-shadow: 0 6px 18px rgba(255,90,54,.3); }
.bps-brand small { display:block; font: 500 .72rem Inter, sans-serif; color: var(--muted); letter-spacing:.02em; }
.bps-side-book { display:flex; gap:.7rem; align-items:center; }
.bps-side-book img, .bps-side-book .ph { width:44px; min-width:44px; border-radius:4px; box-shadow:0 4px 12px rgba(0,0,0,.5); }
.bps-side-book .ph { height:66px; display:flex; align-items:center; justify-content:center; background:#262a3d; }
.bps-side-book b { display:block; font-size:.92rem; line-height:1.2; }
.bps-empty { text-align:center; padding: 2.4rem 1rem; border: 1px dashed var(--line); border-radius: 16px; color: var(--muted); }
.bps-empty .big { font-size: 2.4rem; }

/* ===== Studio Floor: depth, motion, drama ===== */
:root { --acc:#FF5A36; --acc2:#7B5CFF; --ok:#2ED9A0; --s1:#14141F; --s2:#1C1C2A;
  --ease:cubic-bezier(.2,.8,.2,1); --spring:cubic-bezier(.34,1.56,.64,1);
  --e1:0 1px 0 rgba(255,255,255,.05) inset, 0 2px 8px rgba(5,5,12,.35);
  --e2:0 1px 0 rgba(255,255,255,.07) inset, 0 2px 6px rgba(5,5,12,.35), 0 12px 34px rgba(5,5,12,.5), 0 40px 90px rgba(5,5,12,.35);
  --e4:0 2px 6px rgba(255,90,54,.35), 0 10px 30px rgba(255,90,54,.38); }
[data-testid="stAppViewContainer"] { background: #0B0B14; }
[data-testid="stAppViewContainer"]::before { content:""; position:fixed; inset:-20vmax; z-index:0; pointer-events:none;
  background: radial-gradient(38vmax 30vmax at 12% 8%, rgba(255,90,54,.20), transparent 70%),
              radial-gradient(42vmax 34vmax at 92% 30%, rgba(123,92,255,.22), transparent 70%),
              radial-gradient(36vmax 30vmax at 40% 105%, rgba(255,61,110,.14), transparent 70%);
  filter: blur(40px); animation: bps-drift 60s ease-in-out infinite alternate; }
[data-testid="stAppViewContainer"]::after { content:""; position:fixed; z-index:0; pointer-events:none; left:-20%; right:-20%;
  top:12vh; height:34vh; transform: rotate(-14deg);
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.035) 40%, rgba(255,90,54,.05) 70%, transparent); }
@keyframes bps-drift { from { transform: translate3d(0,0,0) scale(1); } to { transform: translate3d(-3vmax,2vmax,0) scale(1.08); } }
@keyframes bps-rise { from { opacity:0; transform: translateY(16px); } to { opacity:1; transform:none; } }
@keyframes bps-pop { 0% { opacity:0; transform: translateY(24px) rotate(-14deg) scale(.88); }
  70% { transform: translateY(-4px) rotate(-5deg) scale(1.02); } 100% { opacity:1; transform: rotate(-6deg); } }
@keyframes bps-pop-c { 0% { opacity:0; transform: translateY(24px) rotate(-12deg) scale(.88); } 100% { opacity:1; transform: rotate(-6deg); } }
@keyframes bps-shine { from { transform: translateX(-120%); } to { transform: translateX(220%); } }
@keyframes bps-draw { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
@keyframes bps-pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(255,90,54,.45); } 50% { box-shadow: 0 0 0 7px rgba(255,90,54,0); } }

/* glass top bar + elevation */
header[data-testid="stHeader"] { background: rgba(11,11,20,.62) !important; backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%); border-bottom: 1px solid rgba(255,255,255,.08); }
[data-testid="stVerticalBlockBorderWrapper"] { background: var(--s1); border-color: rgba(255,255,255,.07) !important;
  border-radius: 20px !important; box-shadow: var(--e1); }
[data-testid="stSidebar"] { background: rgba(19,20,27,.82); backdrop-filter: blur(20px); }

/* primary buttons: the one hot spot */
[data-testid="stBaseButton-primary"], button[kind="primary"] { background: var(--acc) !important; border: 0 !important;
  border-radius: 14px !important; box-shadow: var(--e4); position: relative; overflow: hidden;
  transition: transform .22s var(--spring), box-shadow .22s var(--ease); }
[data-testid="stBaseButton-primary"]:hover { transform: translateY(-2px); box-shadow: 0 3px 8px rgba(255,90,54,.4), 0 16px 40px rgba(255,90,54,.5); }
[data-testid="stBaseButton-primary"]:active { transform: scale(.97); }
[data-testid="stBaseButton-primary"]::after { content:""; position:absolute; inset:0; width:40%;
  background: linear-gradient(100deg, transparent, rgba(255,255,255,.35), transparent); transform: translateX(-120%); }
[data-testid="stBaseButton-primary"]:hover::after { animation: bps-shine .7s var(--ease); }
[data-testid="stBaseButton-secondary"] { border-radius: 14px; transition: transform .2s var(--spring), border-color .2s; }
[data-testid="stBaseButton-secondary"]:active { transform: scale(.97); }

/* entrance rhythm */
.bps-head, .bps-hero2, .bps-tile, .bps-metric, .bps-stat, .bps-empty { animation: bps-rise .55s var(--ease) both; }
.bps-tile:nth-child(2) { animation-delay: .08s; } .bps-tile:nth-child(3) { animation-delay: .16s; }
.bps-title { font-weight: 800; letter-spacing: -.02em; }

/* hero v2: the cover breaks out of its card */
.bps-hero2 { position: relative; margin: 2.4rem 0 2.2rem; padding: 2.4rem 2rem 2.2rem 44%; min-height: 330px;
  display:flex; flex-direction:column; justify-content:center; }
.bps-hero2 .bg { position:absolute; inset:0; border-radius: 28px; overflow:hidden; box-shadow: var(--e2);
  background: linear-gradient(135deg, #1C1C2A, #10101A); border: 1px solid rgba(255,255,255,.07); }
.bps-hero2 .bg::before { content:""; position:absolute; left:-10%; right:-10%; top:48%; height:60%; transform: rotate(-14deg);
  background: linear-gradient(90deg, rgba(255,90,54,0), rgba(255,90,54,.28) 60%, rgba(255,61,110,.18)); }
.bps-hero2 .bg::after { content:""; position:absolute; width:70%; aspect-ratio:1; left:-8%; top:-30%; border-radius:50%;
  background: radial-gradient(circle, rgba(255,90,54,.30), transparent 65%); filter: blur(20px); }
.bps-hero2 .cv { position:absolute; left:6%; top:-34px; width:32%; max-width:250px; border-radius:6px; transform: rotate(-6deg);
  animation: bps-pop .9s var(--ease) .1s both;
  box-shadow: 0 1px 0 rgba(255,255,255,.35) inset, 0 3px 6px rgba(0,0,0,.5), 0 24px 40px rgba(0,0,0,.55), 0 70px 110px rgba(255,90,54,.28); }
.bps-hero2 .cv-ph { aspect-ratio: 2/3; display:flex; align-items:center; justify-content:center; font-size:3.4rem;
  background: linear-gradient(160deg,#2b3350,#161a2a); }
.bps-hero2 .txt { position:relative; }
.bps-hero2 h2 { font: 800 clamp(2rem, 4.6vw, 3.5rem)/.98 Fraunces, Georgia, serif; letter-spacing:-.025em; margin: .2rem 0 .6rem; }
.bps-hero2 .meta { color: var(--muted); margin-bottom: .8rem; }
.bps-hero2 .prog { margin-top:1rem; max-width: 380px; }
.bps-hero2 .prog b { font: 700 .8rem Inter; color: var(--text); }

/* asymmetric momentum tiles */
.bps-mom { display:grid; grid-template-columns: 2fr 1fr; grid-template-rows: 1fr 1fr; gap: 12px; margin-bottom: 2rem; }
.bps-tile { background: var(--s1); border:1px solid rgba(255,255,255,.07); border-radius: 22px; padding: 1.1rem 1.2rem;
  box-shadow: var(--e1); display:flex; flex-direction:column; justify-content:flex-end; min-height: 108px; position:relative;
  transition: transform .3s var(--spring), box-shadow .3s var(--ease); }
.bps-tile:hover { transform: translateY(-3px); box-shadow: var(--e2); }
.bps-tile .l { color: var(--muted); font: 650 .7rem Inter; letter-spacing:.12em; text-transform: uppercase; }
.bps-tile .v { font: 800 2.1rem/1 Fraunces, Georgia, serif; margin-top:.3rem; letter-spacing:-.02em; }
.bps-tile .s { color: var(--muted); font-size:.8rem; margin-top:.25rem; }
.bps-tile.big { grid-row: span 2; background: linear-gradient(150deg, #241528, #14141F 60%); overflow: visible; }
.bps-tile.big .v { font-size: clamp(3rem, 9vw, 5.2rem); color: #fff; text-shadow: 0 0 40px rgba(255,90,54,.45); }
.bps-tile.big .badge { position:absolute; top:-12px; right:16px; background: var(--acc); color:#0B0B14; font: 800 .72rem Inter;
  padding:.3rem .7rem; border-radius:999px; box-shadow: var(--e4); transform: rotate(3deg); }

/* metric hero + sparkline that runs off the card */
.bps-metric { position:relative; margin: .5rem 0 2.4rem; padding: 1.6rem 1.6rem 6.5rem; border-radius: 28px; overflow: visible;
  background: linear-gradient(160deg,#1C1C2A,#10101A); border:1px solid rgba(255,255,255,.07); box-shadow: var(--e2); }
.bps-metric .l { color: var(--muted); font: 650 .72rem Inter; letter-spacing:.14em; text-transform:uppercase; }
.bps-metric .v { font: 800 clamp(3.4rem, 13vw, 6.2rem)/.95 Fraunces, Georgia, serif; letter-spacing:-.03em; margin:.3rem 0;
  text-shadow: 0 0 50px rgba(255,90,54,.4); }
.bps-metric .s { color: var(--muted); }
.bps-metric svg { position:absolute; left:-4%; width:108%; bottom:-14px; height:130px; overflow:visible; pointer-events:none; }
.bps-metric svg path.line { stroke-dasharray:1; stroke-dashoffset:1; animation: bps-draw 1.4s var(--ease) .2s forwards; }

.bps-check.next .dot { animation: bps-pulse 2s infinite; }

@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  .bps-hero2 { padding: 175px 1.3rem 1.6rem; margin-top: 4.2rem; }
  .bps-hero2 .cv { left: 50%; margin-left: -23%; width: 46%; top: -64px; animation-name: bps-pop-c; }
  .bps-mom { grid-template-columns: 1.6fr 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
  .bps-metric svg path.line { stroke-dashoffset: 0; }
}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(s) -> str:
    return html.escape(str(s or ""))


def md(html_str: str) -> None:
    st.markdown(html_str, unsafe_allow_html=True)


def chip(text: str, tone: str = "") -> str:
    return f'<span class="bps-chip {tone}">{esc(text)}</span>'


def chips(items: list[tuple[str, str]] | list[str]) -> None:
    md("".join(chip(*i) if isinstance(i, tuple) else chip(i) for i in items))


def header(eyebrow: str, title: str, sub: str = "") -> None:
    md(f'<div class="bps-head"><div class="bps-eyebrow">{esc(eyebrow)}</div><h1 class="bps-title">{esc(title)}</h1>'
       + (f'<div class="bps-sub">{esc(sub)}</div>' if sub else "") + "</div>")


def stat(label: str, value: str, sub: str = "") -> str:
    return (f'<div class="bps-stat"><div class="l">{esc(label)}</div><div class="v">{esc(value)}</div>'
            + (f'<div class="s">{esc(sub)}</div>' if sub else "") + "</div>")


def stats(items: list[tuple]) -> None:
    for col, item in zip(st.columns(len(items)), items):
        with col:
            md(stat(*item))


def bar(frac: float) -> str:
    return f'<div class="bps-bar"><div style="width:{max(0, min(1, frac)) * 100:.1f}%"></div></div>'


@st.cache_data(show_spinner=False, max_entries=64)
def _img_uri(path: str, mtime: float, width: int) -> str:
    from PIL import Image
    import io
    img = Image.open(path).convert("RGB")
    img.thumbnail((width, width * 2))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def img_uri(path: Path | None, width: int = 240) -> str | None:
    if not path or not Path(path).exists():
        return None
    return _img_uri(str(path), Path(path).stat().st_mtime, width)


def scene_seconds(s: dict) -> float:
    words = len((s.get("voiceover") or "").split())
    return max(1.2, words / 2.6 + 0.4) if words else float(s.get("seconds") or 3)


def timeline(scenes: list[dict]) -> str:
    cells = []
    for s in scenes:
        vis = s.get("visual", "cover")
        secs = scene_seconds(s)
        tip = esc(f"{VISUAL_LABEL.get(vis, vis)} · {secs:.1f}s · {s.get('voiceover') or s.get('overlay') or ''}")
        cells.append(f'<div class="sc t-{esc(vis)}" style="--w:{secs:.2f}" title="{tip}">'
                     f'<span class="ic">{VISUAL_ICON.get(vis, "▪")}</span><span class="bt">{esc(s.get("beat", ""))}</span></div>')
    return f'<div class="bps-tl">{"".join(cells)}</div>'


def legend(kinds: list[str] | None = None) -> None:
    kinds = kinds or list(VISUAL_ICON)
    md('<div class="bps-legend">' + "".join(f'<span><i class="t-{k}"></i>{VISUAL_LABEL[k]}</span>' for k in kinds)
       + "</div>")


def hero(cover_uri: str | None, icon: str, eyebrow: str, title: str, meta: str, chips_html: str, done: int,
         total: int) -> None:
    """Studio hero: the cover is tilted and breaks out of the card's top edge."""
    cv = (f'<img class="cv" src="{cover_uri}">' if cover_uri else f'<div class="cv cv-ph">{icon}</div>')
    md(f'<div class="bps-hero2"><div class="bg"></div>{cv}<div class="txt">'
       f'<div class="bps-eyebrow">{esc(eyebrow)}</div><h2>{esc(title)}</h2><div class="meta">{esc(meta)}</div>{chips_html}'
       f'<div class="prog"><b>Set-up {done}/{total}</b>{bar(done / total if total else 0)}</div></div></div>')


def momentum(big: tuple, small: list[tuple]) -> None:
    """One dominant tile (2/3 width, full height) beside two small ones. big = (label, value, sub, badge)."""
    label, value, sub, badge = big
    tiles = ('<div class="bps-tile big">' + (f'<span class="badge">{esc(badge)}</span>' if badge else "")
             + f'<div class="l">{esc(label)}</div><div class="v">{esc(value)}</div><div class="s">{esc(sub)}</div></div>')
    for lab, val, sb in small:
        tiles += (f'<div class="bps-tile"><div class="l">{esc(lab)}</div><div class="v">{esc(val)}</div>'
                  f'<div class="s">{esc(sb)}</div></div>')
    md(f'<div class="bps-mom">{tiles}</div>')


def sparkline(values: list[float], w: int = 400, h: int = 120) -> str:
    """Glowing smooth curve, drawn on load. Empty string with fewer than 2 points."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = [(i / (len(values) - 1) * w, h - 12 - (v - lo) / span * (h - 30)) for i, v in enumerate(values)]
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        mx = (x0 + x1) / 2
        d += f" C{mx:.1f},{y0:.1f} {mx:.1f},{y1:.1f} {x1:.1f},{y1:.1f}"
    area = d + f" L{w},{h} L0,{h} Z"
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none"><defs>'
            f'<linearGradient id="sg" x1="0" x2="1"><stop offset="0" stop-color="#7B5CFF"/><stop offset="1" stop-color="#FF5A36"/></linearGradient>'
            f'<linearGradient id="sa" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF5A36" stop-opacity=".28"/>'
            f'<stop offset="1" stop-color="#FF5A36" stop-opacity="0"/></linearGradient>'
            f'<filter id="gl" x="-10%" y="-50%" width="120%" height="200%"><feGaussianBlur stdDeviation="5"/></filter></defs>'
            f'<path d="{area}" fill="url(#sa)"/>'
            f'<path d="{d}" fill="none" stroke="#FF5A36" stroke-width="7" opacity=".55" filter="url(#gl)"/>'
            f'<path class="line" d="{d}" fill="none" stroke="url(#sg)" stroke-width="3.5" stroke-linecap="round" pathLength="1"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="6" fill="#fff"/></svg>')


def metric(label: str, value: str, sub: str, values: list[float]) -> None:
    md(f'<div class="bps-metric"><div class="l">{esc(label)}</div><div class="v">{esc(value)}</div>'
       f'<div class="s">{esc(sub)}</div>{sparkline(values)}</div>')


def empty(icon: str, text: str) -> None:
    md(f'<div class="bps-empty"><div class="big">{icon}</div>{esc(text)}</div>')

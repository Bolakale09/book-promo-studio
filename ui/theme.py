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
:root { --gold:#F0B429; --gold2:#F7D27A; --card:#181A23; --card2:#1D2030; --line:#2A2D38; --muted:#9C978E;
        --text:#ECE7DF; }
.block-container { padding-top: 4.6rem; padding-bottom: 5rem; max-width: 1260px; }
[data-testid="stBaseButton-primary"], button[kind="primary"] { color:#1B1400 !important; font-weight:650; }
[data-testid="stBaseButton-primary"] p { color:#1B1400 !important; }
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
  background: radial-gradient(120% 160% at 0% 0%, rgba(240,180,41,.20), transparent 55%),
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
.bps-chip.gold { background: rgba(240,180,41,.13); border-color: rgba(240,180,41,.45); color: var(--gold2); }
.bps-chip.green { background: rgba(76,175,120,.14); border-color: rgba(76,175,120,.45); color:#8FE0B0; }
.bps-chip.red { background: rgba(230,90,80,.14); border-color: rgba(230,90,80,.45); color:#F4A49B; }
.bps-chip.blue { background: rgba(110,160,240,.14); border-color: rgba(110,160,240,.45); color:#A9C6F5; }

/* progress + checklist */
.bps-bar { height: 8px; background: rgba(255,255,255,.07); border-radius: 99px; overflow: hidden; margin:.4rem 0 .2rem; }
.bps-bar > div { height: 100%; background: linear-gradient(90deg,#E0892F,#F0B429,#F7D27A); border-radius: 99px; }
.bps-check { display:flex; align-items:center; gap:.75rem; padding:.62rem .1rem; border-bottom:1px dashed var(--line); }
.bps-check:last-child { border-bottom: 0; }
.bps-check .dot { width:24px; height:24px; min-width:24px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-size:.74rem; font-weight:700; border:1.5px solid var(--line); color: var(--muted); }
.bps-check.done .dot { background:#2F8A57; border-color:#2F8A57; color:#fff; }
.bps-check.next .dot { border-color: var(--gold); color: var(--gold); box-shadow: 0 0 0 4px rgba(240,180,41,.16); }
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
.t-page { background:#EADFC6; } .t-flip { background:#D9C8A0; } .t-cover { background:#F0B429; }
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
  background: radial-gradient(90% 90% at 30% 20%, rgba(240,180,41,.25), transparent 60%), linear-gradient(160deg,#2a2f45,#161923); }
.bps-brand { display:flex; align-items:center; gap:.65rem; font-family: Fraunces, Georgia, serif; font-weight:700;
  font-size:1.2rem; margin: -.4rem 0 .9rem; line-height: 1.15; }
.bps-brand .logo { width:36px; height:36px; border-radius:10px; display:flex; align-items:center; justify-content:center;
  background: linear-gradient(135deg,#F0B429,#E0702F); font-size:1.15rem; box-shadow: 0 6px 18px rgba(240,140,40,.3); }
.bps-brand small { display:block; font: 500 .72rem Inter, sans-serif; color: var(--muted); letter-spacing:.02em; }
.bps-side-book { display:flex; gap:.7rem; align-items:center; }
.bps-side-book img, .bps-side-book .ph { width:44px; min-width:44px; border-radius:4px; box-shadow:0 4px 12px rgba(0,0,0,.5); }
.bps-side-book .ph { height:66px; display:flex; align-items:center; justify-content:center; background:#262a3d; }
.bps-side-book b { display:block; font-size:.92rem; line-height:1.2; }
.bps-empty { text-align:center; padding: 2.4rem 1rem; border: 1px dashed var(--line); border-radius: 16px; color: var(--muted); }
.bps-empty .big { font-size: 2.4rem; }
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


def empty(icon: str, text: str) -> None:
    md(f'<div class="bps-empty"><div class="big">{icon}</div>{esc(text)}</div>')

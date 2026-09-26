"""Monthly spend guard. Every paid API call goes through `guard()` first and `record()` after.

Prices are estimates in USD (checked Sept 2026). Unknown models use a conservative fallback.
"""
import json
import threading
from datetime import datetime

from . import config

_lock = threading.Lock()

# per 1M tokens: (input, output)
CHAT_PRICES = {
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o-mini": (0.15, 0.60),
    "grok-build-0.1": (1.00, 2.00),
    "grok-4.3": (1.25, 2.50),
    "grok-4.7": (2.00, 6.00),
}
CHAT_FALLBACK = (2.00, 8.00)

TTS_PER_CHAR = {"gpt-4o-mini-tts": 12 / 1e6, "tts-1": 15 / 1e6, "tts-1-hd": 30 / 1e6, "grok-tts": 4.2 / 1e6}
WHISPER_PER_MIN = 0.006
XAI_STT_PER_MIN = 0.003  # conservative

# per portrait image
IMAGE_PRICES = {
    ("gpt-image-1-mini", "low"): 0.005,
    ("gpt-image-1-mini", "medium"): 0.015,
    ("gpt-image-1-mini", "high"): 0.052,
    ("gpt-image-1.5", "low"): 0.02,
    ("gpt-image-1.5", "medium"): 0.06,
    ("gpt-image-1.5", "high"): 0.25,
    ("grok-imagine-image", None): 0.02,
    ("grok-imagine-image-2.0", None): 0.04,
    ("grok-imagine-image-quality", None): 0.05,
}
IMAGE_FALLBACK = 0.08

# per second of generated video
VIDEO_PER_SEC = {
    "grok-imagine-video": 0.07,      # 720p
    "grok-imagine-video-1.5": 0.14,  # 720p
    "sora-2": 0.10,
    "sora-2-pro": 0.30,
}
VIDEO_FALLBACK = 0.30


class BudgetExceeded(RuntimeError):
    pass


def _month() -> str:
    return datetime.now().strftime("%Y-%m")


def _load() -> list:
    if config.BUDGET_FILE.exists():
        return json.loads(config.BUDGET_FILE.read_text(encoding="utf-8"))
    return []


def spent_this_month() -> float:
    m = _month()
    return round(sum(e["cost"] for e in _load() if e["month"] == m), 4)


def remaining() -> float:
    return round(config.MONTHLY_BUDGET_USD - spent_this_month(), 4)


def guard(estimated_cost: float, what: str) -> None:
    left = remaining()
    if estimated_cost > left:
        raise BudgetExceeded(
            f"'{what}' would cost about ${estimated_cost:.3f} but only ${left:.3f} of your "
            f"${config.MONTHLY_BUDGET_USD:.2f} monthly budget is left."
        )


def record(service: str, model: str, cost: float, note: str = "") -> None:
    with _lock:
        entries = _load()
        entries.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "month": _month(),
            "service": service,
            "model": model,
            "cost": round(cost, 5),
            "note": note[:120],
        })
        config.BUDGET_FILE.write_text(json.dumps(entries, indent=1), encoding="utf-8")


def recent(n: int = 30) -> list:
    return list(reversed(_load()))[:n]


# ---- estimators -------------------------------------------------------------

def chat_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    pi, po = CHAT_PRICES.get(model, CHAT_FALLBACK)
    return in_tokens / 1e6 * pi + out_tokens / 1e6 * po


def tts_cost(model: str, chars: int) -> float:
    return chars * TTS_PER_CHAR.get(model, 30 / 1e6)


def image_cost(model: str, quality: str | None) -> float:
    return IMAGE_PRICES.get((model, quality)) or IMAGE_PRICES.get((model, None)) or IMAGE_FALLBACK


def video_cost(model: str, seconds: float) -> float:
    return seconds * VIDEO_PER_SEC.get(model, VIDEO_FALLBACK)

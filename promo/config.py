"""Central settings. Everything can be overridden in the .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "5")  # fail fast when Hugging Face is unreachable
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "20")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

DATA = ROOT / "data"
BOOKS_DIR = DATA / "books"
REFS_DIR = DATA / "references"
BLUEPRINTS_DIR = DATA / "blueprints"
PROJECTS_DIR = DATA / "projects"
BROLL_DIR = DATA / "broll"
MUSIC_DIR = DATA / "music"
BUDGET_FILE = DATA / "budget.json"

for _d in (BOOKS_DIR, REFS_DIR, BLUEPRINTS_DIR, PROJECTS_DIR, BROLL_DIR, MUSIC_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


OPENAI_API_KEY = env("OPENAI_API_KEY")
XAI_API_KEY = env("XAI_API_KEY")
PEXELS_API_KEY = env("PEXELS_API_KEY")  # free at pexels.com/api

MONTHLY_BUDGET_USD = float(env("MONTHLY_BUDGET_USD", "20"))

# Text / script model: "openai" or "xai"
LLM_PROVIDER = env("LLM_PROVIDER", "openai")
LLM_MODEL = env("LLM_MODEL", "gpt-5-mini" if LLM_PROVIDER == "openai" else "grok-4.3")
LLM_REASONING_EFFORT = env("LLM_REASONING_EFFORT", "low")

# Voice
TTS_MODEL = env("TTS_MODEL", "gpt-4o-mini-tts")

# Images: "openai" or "xai"
IMAGE_PROVIDER = env("IMAGE_PROVIDER", "openai")
IMAGE_MODEL = env("IMAGE_MODEL", "gpt-image-1-mini" if IMAGE_PROVIDER == "openai" else "grok-imagine-image")
IMAGE_QUALITY = env("IMAGE_QUALITY", "medium")  # openai: low | medium | high

# AI video clips (optional per scene): "xai" or "openai"
VIDEO_PROVIDER = env("VIDEO_PROVIDER", "xai")
VIDEO_MODEL = env("VIDEO_MODEL", "grok-imagine-video" if VIDEO_PROVIDER == "xai" else "sora-2")
VIDEO_RESOLUTION = env("VIDEO_RESOLUTION", "720p")

# Local transcription (free). tiny.en / base.en / small.en
WHISPER_MODEL = env("WHISPER_MODEL", "base.en")

# Output video
W, H, FPS = 1080, 1920, 30

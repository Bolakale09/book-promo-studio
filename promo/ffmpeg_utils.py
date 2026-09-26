import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from . import config


@lru_cache
def ffmpeg_exe() -> str:
    local = config.ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if local.exists():
        return str(local)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("FFmpeg not found. Run setup.bat or install FFmpeg.")


def run(args: list, cwd: str | Path | None = None) -> str:
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *map(str, args)]
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{' '.join(cmd)}\n\n{p.stderr[-3000:]}")
    return p.stderr


def duration(path: str | Path) -> float:
    """Media duration in seconds (parsed from ffmpeg's header output, so no ffprobe needed)."""
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
    if not m:
        raise RuntimeError(f"Could not read duration of {path}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


@lru_cache
def has_libass() -> bool:
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-filters"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return re.search(r"^\s*\S*\s+ass\s", p.stdout, re.M) is not None

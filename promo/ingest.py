"""Download a reference video and pull out audio, keyframes and shot cuts."""
import hashlib
import json
import re
import shutil
from pathlib import Path

from . import config, ffmpeg_utils as ff


def ref_id_for(url_or_name: str) -> str:
    return hashlib.md5(url_or_name.encode()).hexdigest()[:10]


def download(url: str) -> Path:
    import yt_dlp

    folder = config.REFS_DIR / ref_id_for(url)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "video.mp4"
    if out.exists():
        return out
    opts = {
        "outtmpl": str(folder / "video.%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "ffmpeg_location": str(Path(ff.ffmpeg_exe()).parent),
        "quiet": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    (folder / "info.json").write_text(json.dumps({
        "url": url, "title": info.get("title"), "uploader": info.get("uploader"),
        "duration": info.get("duration"), "view_count": info.get("view_count"),
        "like_count": info.get("like_count"), "description": (info.get("description") or "")[:2000],
    }, indent=1), encoding="utf-8")
    if not out.exists():  # yt-dlp may have kept another extension
        cand = next((p for p in folder.glob("video.*") if p.suffix != ".json"), None)
        if not cand:
            raise RuntimeError("Download finished but no video file was found.")
        ff.run(["-i", cand, "-c", "copy", out])
    return out


def import_local(file_path: Path, original_name: str) -> Path:
    folder = config.REFS_DIR / ref_id_for(original_name + str(file_path.stat().st_size))
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "video.mp4"
    if not out.exists():
        ff.run(["-i", file_path, "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", out])
    (folder / "info.json").write_text(json.dumps({"url": None, "title": original_name}), encoding="utf-8")
    return out


def extract_audio(video: Path) -> Path:
    wav = video.with_name("audio.wav")
    if not wav.exists():
        ff.run(["-i", video, "-vn", "-ac", "1", "-ar", "16000", wav])
    return wav


def shot_cuts(video: Path, threshold: float = 0.3) -> list[float]:
    """Timestamps (s) where the picture changes - tells us the pacing of the reference."""
    log = ff.run(["-loglevel", "info", "-i", video, "-vf", f"select='gt(scene,{threshold})',showinfo",
                  "-an", "-f", "null", "-"])
    return [round(float(t), 2) for t in re.findall(r"pts_time:([\d.]+)", log)]


def keyframes(video: Path, max_frames: int = 8) -> list[Path]:
    """Evenly spaced small frames, used to read on-screen text overlays."""
    folder = video.parent / "frames"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
    dur = ff.duration(video)
    n = max(2, min(max_frames, int(dur // 1.5) or 2))
    paths = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        p = folder / f"f{i:02d}_{t:05.1f}s.jpg"
        ff.run(["-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", "scale=512:-2", "-q:v", "4", p])
        paths.append(p)
    return paths

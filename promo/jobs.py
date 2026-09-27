"""Renders run in their own process, so the app stays responsive and a browser refresh never kills a render."""
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

from . import config

JOBS_DIR = config.DATA / "jobs"
STALE_SECONDS = 15 * 60  # no progress for this long = the worker died


def _write(d: Path, **status) -> None:
    status["updated"] = time.time()
    tmp = d / "status.tmp"
    tmp.write_text(json.dumps(status), encoding="utf-8")
    tmp.replace(d / "status.json")


def start(book_id: str, variant: dict, options: dict) -> str:
    job_id = time.strftime("%Y%m%d-%H%M%S")
    d = JOBS_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "job.json").write_text(json.dumps({"book_id": book_id, "variant": variant, "options": options}),
                                encoding="utf-8")
    _write(d, state="queued", msg="Starting...", frac=0.0, book_id=book_id, name=variant.get("name", "video"))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log = open(d / "log.txt", "w", encoding="utf-8")
    subprocess.Popen([sys.executable, "-m", "promo.jobs", str(d)], cwd=config.ROOT, stdout=log,
                     stderr=subprocess.STDOUT, creationflags=flags)
    return job_id


def status(job_id: str) -> dict:
    p = JOBS_DIR / job_id / "status.json"
    if not p.exists():
        return {"state": "missing"}
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"state": "running", "msg": "...", "frac": 0}
    if s["state"] in ("queued", "running") and time.time() - s.get("updated", 0) > STALE_SECONDS:
        s["state"], s["error"] = "error", "The render stopped responding (was the app closed?)."
    s["id"] = job_id
    return s


def recent(book_id: str, limit: int = 5) -> list[dict]:
    out = []
    for d in sorted(JOBS_DIR.glob("*"), reverse=True)[:40]:
        s = status(d.name)
        if s.get("book_id") == book_id:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def _run(d: Path) -> None:
    from . import book as bk, render

    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    base = {"book_id": job["book_id"], "name": job["variant"].get("name", "video")}
    last = {"frac": 0.0}

    def progress(msg, frac=None):
        if frac is not None:
            last["frac"] = frac
        _write(d, state="running", msg=msg, frac=last["frac"], **base)

    try:
        opts = dict(job["options"])
        if opts.get("music"):
            opts["music"] = Path(opts["music"])
        out = render.render(bk.load(job["book_id"]), job["variant"], progress=progress, **opts)
        _save_to_cloud(progress)
        _write(d, state="done", msg="Done!", frac=1.0, result=str(out), **base)
    except Exception as e:
        traceback.print_exc()
        _save_to_cloud(lambda *a, **k: None)  # keep whatever was paid for (images, clips, spending log)
        _write(d, state="error", msg="Failed", frac=last["frac"], error=f"{type(e).__name__}: {e}", **base)


def _save_to_cloud(progress) -> None:
    from . import storage
    if storage.enabled():
        try:
            progress("Saving to cloud storage...", 0.99)
            storage.sync_up()
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    _run(Path(sys.argv[1]))

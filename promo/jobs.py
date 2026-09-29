"""Background tasks. Each runs in its own process, so the app stays responsive, you can leave the page, and a
browser refresh never cancels paid work.

Kinds:
  render / quick / redo      heavy (use the CPU): they wait in a queue and run one at a time
  scripts / variations / digest / portrait / desk      light (just API calls): run straight away
"""
import json
import secrets
import subprocess
import sys
import time
import traceback
from pathlib import Path

from . import config

JOBS_DIR = config.DATA / "jobs"
STALE_SECONDS = 15 * 60  # no progress for this long = the worker died
HEAVY = {"render", "quick", "redo"}
LABELS = {"render": "Rendering", "quick": "Quick video", "redo": "Redoing a scene", "scripts": "Writing scripts",
          "variations": "Writing variations", "digest": "Reading the manuscript", "portrait": "Creating a portrait",
          "desk": "Creating a desk photo"}


def _write(d: Path, **status) -> None:
    """Update a task's status. Never fatal: on Windows another process may be reading the file right now,
    so retry briefly and otherwise skip this update (the next one will get through)."""
    status["updated"] = time.time()
    data = json.dumps(status)
    final = status.get("state") in ("done", "error")
    for attempt in range(60 if final else 8):
        try:
            tmp = d / f"status.{secrets.token_hex(3)}.tmp"
            tmp.write_text(data, encoding="utf-8")
            try:
                tmp.replace(d / "status.json")
            finally:
                tmp.unlink(missing_ok=True)
            return
        except OSError:
            time.sleep(0.05 + 0.05 * attempt)


def start(kind: str, book_id: str, name: str, payload: dict | None = None) -> str:
    ns = time.time_ns()  # one clock reading -> ids sort exactly in the order tasks were started (= queue order)
    job_id = f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(ns // 10**9))}-{ns % 10**9:09d}"
    d = JOBS_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "job.json").write_text(json.dumps({"kind": kind, "book_id": book_id, "name": name,
                                            "payload": payload or {}}), encoding="utf-8")
    _write(d, state="queued", msg="Waiting to start..." if kind in HEAVY else "Starting...", frac=0.0,
           book_id=book_id, name=name, kind=kind)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log = open(d / "log.txt", "w", encoding="utf-8")
    subprocess.Popen([sys.executable, "-m", "promo.jobs", str(d)], cwd=config.ROOT, stdout=log,
                     stderr=subprocess.STDOUT, creationflags=flags)
    return job_id


def start_render(book_id: str, variant: dict, options: dict) -> str:
    return start("render", book_id, variant.get("name", "video"), {"variant": variant, "options": options})


def status(job_id: str) -> dict:
    p = JOBS_DIR / job_id / "status.json"
    if not p.exists():
        return {"state": "missing", "id": job_id}
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"state": "running", "msg": "...", "frac": 0, "id": job_id}
    if s["state"] in ("queued", "running") and time.time() - s.get("updated", 0) > STALE_SECONDS:
        s["state"], s["error"] = "error", "This task stopped responding (was the app restarted?)."
    s["id"] = job_id
    s.setdefault("kind", "render")
    return s


def _all(limit: int = 80) -> list[dict]:
    if not JOBS_DIR.exists():
        return []
    return [status(d.name) for d in sorted(JOBS_DIR.glob("*"), reverse=True)[:limit] if d.is_dir()]


def recent(book_id: str, limit: int = 5, kinds: set | None = None) -> list[dict]:
    out = [s for s in _all() if s.get("book_id") == book_id and (not kinds or s.get("kind") in kinds)]
    return out[:limit]


def active(book_id: str | None = None, kinds: set | None = None) -> list[dict]:
    return [s for s in _all() if s["state"] in ("queued", "running")
            and (book_id is None or s.get("book_id") == book_id) and (not kinds or s.get("kind") in kinds)]


def queue() -> list[dict]:
    """Heavy tasks waiting or running, oldest first."""
    return sorted(active(kinds=HEAVY), key=lambda s: s["id"])


# ---- the worker process ------------------------------------------------------------------

def _wait_turn(d: Path, job_id: str, base: dict) -> None:
    """Heavy tasks run one at a time, oldest first, so renders don't fight over the CPU (or the web server's
    memory)."""
    while True:
        ahead = [s for s in queue() if s["id"] < job_id]
        if not ahead:
            return
        _write(d, state="queued", msg=f"Waiting in line - {len(ahead)} ahead", frac=0.0, **base)
        time.sleep(3)


def _run(d: Path) -> None:
    from . import book as bk, render, script, visuals

    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    kind, payload = job.get("kind", "render"), job.get("payload") or {}
    if "variant" in job and "payload" not in job:  # jobs written by older versions
        payload = {"variant": job["variant"], "options": job.get("options", {})}
    base = {"book_id": job["book_id"], "name": job.get("name") or payload.get("variant", {}).get("name", "video"),
            "kind": kind}
    last = {"frac": 0.0}

    def progress(msg, frac=None):
        if frac is not None:
            last["frac"] = frac
        _write(d, state="running", msg=msg, frac=last["frac"], **base)

    try:
        if kind in HEAVY:
            _wait_turn(d, d.name, base)
        progress(LABELS.get(kind, "Working") + "...", 0.02)
        book = bk.load(job["book_id"])
        result = ""
        if kind == "render":
            opts = dict(payload.get("options") or {})
            if opts.get("music"):
                opts["music"] = Path(opts["music"])
            render.render(book, payload["variant"], progress=progress, **opts)
            result = f"Video '{base['name']}'"
        elif kind == "redo":
            render.redo_scene(book, payload["render_dir"], int(payload["scene"]), payload.get("prompt", ""),
                              progress=progress)
            result = f"New version of '{base['name']}'"
        elif kind == "quick":
            _quick_video(book, payload, progress)
            result = "Your quick video"
        elif kind == "scripts":
            variants = script.generate(book, payload["blueprint"], **payload.get("args", {}))
            script.add_scripts(book["id"], variants, payload.get("source", "builtin"))
            result = f"{len(variants)} new scripts"
        elif kind == "variations":
            variants = script.variations(book, payload["winner"], payload["change"])
            script.add_scripts(book["id"], variants, f"variation of {payload['winner'].get('name')}")
            result = f"{len(variants)} variations"
        elif kind == "digest":
            bk.build_digest(book)
            result = "Manuscript read"
        elif kind == "portrait":
            char = next(c for c in book.get("characters", []) if c["name"] == payload["name"])
            img = visuals.make_character_reference(book, char)
            fresh = bk.load(book["id"])  # save only this change, keep edits made meanwhile
            for c in fresh.get("characters", []):
                if c["name"] == payload["name"]:
                    c["ref_image"] = str(img.relative_to(bk.book_dir(book["id"]))).replace("\\", "/")
            bk.save(fresh)
            result = f"Portrait of {payload['name']}"
        elif kind == "desk":
            visuals.make_background(book)
            result = "Desk photo"
        else:
            raise ValueError(f"Unknown task: {kind}")
        _save_to_cloud(progress)
        _write(d, state="done", msg="Done!", frac=1.0, result=result, **base)
    except Exception as e:
        traceback.print_exc()
        _save_to_cloud(lambda *a, **k: None)  # keep whatever was paid for (images, clips, spending log)
        _write(d, state="error", msg="Failed", frac=last["frac"], error=f"{type(e).__name__}: {e}", **base)


def _quick_video(book: dict, payload: dict, progress) -> Path:
    """One click: read the book (if needed) -> write scripts -> render the strongest."""
    from . import book as bk, render, script
    from .genres import default_blueprint

    if not book.get("digest") and bk.path(book, "manuscript"):
        progress("Reading your manuscript...", 0.04)
        bk.build_digest(book)
        book = bk.load(book["id"])
    progress("Writing scripts...", 0.08)
    args = dict(payload.get("args") or {})
    variants = script.generate(book, default_blueprint(book["genre"]), **args)
    if not variants:
        raise RuntimeError("The AI didn't return any scripts - try again.")
    script.add_scripts(book["id"], variants, "quick video")
    best = variants[0]  # the script writer lists the strongest first
    progress(f"Rendering '{best.get('name')}'...", 0.12)
    return render.render(book, best, progress=lambda m, f=None: progress(m, None if f is None else 0.12 + 0.88 * f),
                         **(payload.get("options") or {}))


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

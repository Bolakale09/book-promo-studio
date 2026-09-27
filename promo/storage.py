"""Cloud storage: keep the whole data/ folder in Cloudflare R2 so nothing is lost when the web app sleeps.

- restore(): on start-up, download everything that isn't on this machine yet (rendered videos stay in the
  cloud and are streamed on demand, so waking up stays fast)
- sync_up(): upload new/changed files and remove files you deleted; runs in the background after every
  action and at the end of every render
- backup / restore of one book as a zip, which works with or without R2

R2 is S3-compatible, so this uses boto3. Settings: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
R2_BUCKET (and optionally R2_PREFIX, default "book-promo-studio").
"""
import io
import json
import mimetypes
import os
import re
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import config

INDEX = config.DATA / ".sync_index.json"
SKIP_DIRS = ("jobs/", "sfx/", "references/")            # temporary or re-creatable
SKIP_NAMES = {"pages.json", "video_only.mp4", "segments.txt", ".sync_index.json", ".restored"}
MARKER = config.DATA / ".restored"  # this server holds the restored library -> safe to upload
SKIP_SUFFIXES = (".tmp", ".part")
LAZY = re.compile(r"^projects/[^/]+/[^/]+/final\.mp4$")  # rendered videos: streamed from R2, not restored

_lock = threading.Lock()
state = {"restored": False, "running": False, "again": False, "last_sync": None, "last_error": None,
         "uploaded": 0, "deleted": 0, "restore": None}


def enabled() -> bool:
    return all([config.R2_ACCOUNT_ID or config.R2_ENDPOINT, config.R2_ACCESS_KEY_ID, config.R2_SECRET_ACCESS_KEY,
                config.R2_BUCKET])


_client_cache: dict = {}


def _clean(v: str) -> str:
    """Settings pasted with quotes or spaces still work."""
    return (v or "").strip().strip('"').strip("'").strip()


def _account() -> tuple[str, str]:
    """(account id, jurisdiction). Also accepts the full endpoint URL pasted as the account id."""
    a = _clean(config.R2_ACCOUNT_ID)
    m = re.search(r"([0-9a-fA-F]{32})(\.eu|\.fedramp)?\.r2\.cloudflarestorage\.com", a)
    return (m.group(1).lower(), m.group(2) or "") if m else (a, "")


def _bucket() -> str:
    b = _clean(config.R2_BUCKET)
    return b.rstrip("/").rsplit("/", 1)[-1] if "cloudflarestorage.com" in b else b


_found_endpoint: dict = {"url": None}  # set when the bucket turned out to live in the EU jurisdiction


def _endpoint() -> str:
    acct, jur = _account()
    return (_clean(config.R2_ENDPOINT) or _found_endpoint["url"]
            or f"https://{acct}{jur}.r2.cloudflarestorage.com")


def _make_client(endpoint: str):
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id=_clean(config.R2_ACCESS_KEY_ID),
        aws_secret_access_key=_clean(config.R2_SECRET_ACCESS_KEY), region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 4, "mode": "standard"},
                      connect_timeout=10, read_timeout=120))


def client():
    key = (_endpoint(), config.R2_ACCESS_KEY_ID, config.R2_SECRET_ACCESS_KEY)
    if key not in _client_cache:
        _client_cache[key] = _make_client(key[0])
    return _client_cache[key]


def _try_eu_endpoint(error: Exception) -> bool:
    """A bucket in the EU jurisdiction only answers on <account>.eu.r2...; try it before giving up."""
    acct, jur = _account()
    if config.R2_ENDPOINT or jur or _found_endpoint["url"] or not any(
            code in str(error) for code in ("Unauthorized", "NoSuchBucket", "AccessDenied", "InvalidAccessKeyId")):
        return False
    url = f"https://{acct}.eu.r2.cloudflarestorage.com"
    try:
        _make_client(url).list_objects_v2(Bucket=_bucket(), MaxKeys=1)
    except Exception:
        return False
    _found_endpoint["url"] = url
    return True


def diagnose() -> list[str]:
    """Spot the usual set-up mistakes from the SHAPE of each setting (values are never shown)."""
    tips = []
    acct, _ = _account()
    ak, sk, b = _clean(config.R2_ACCESS_KEY_ID), _clean(config.R2_SECRET_ACCESS_KEY), _bucket()
    if not config.R2_ENDPOINT and not re.fullmatch(r"[0-9a-fA-F]{32}", acct):
        tips.append(f"R2_ACCOUNT_ID doesn't look like a Cloudflare Account ID (it's {len(acct)} characters; an "
                    "Account ID is 32 letters/numbers). Copy it from the R2 overview page ('Account ID'), "
                    "not the token ID or bucket name.")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", ak):
        tips.append(f"R2_ACCESS_KEY_ID is {len(ak)} characters; an R2 Access Key ID is usually 32. Use the "
                    "'Access Key ID' shown after creating the R2 API token.")
    if len(sk) == 40:
        tips.append("R2_SECRET_ACCESS_KEY is 40 characters, which is the length of the token's 'Token value'. Use "
                    "the 'Secret Access Key' instead (usually 64 characters) - it's shown on the same screen.")
    elif not re.fullmatch(r"[0-9a-fA-F]{64}", sk):
        tips.append(f"R2_SECRET_ACCESS_KEY is {len(sk)} characters; an R2 Secret Access Key is usually 64.")
    if ak and sk and ak == sk:
        tips.append("R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are the same value - they must be different.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", b):
        tips.append("R2_BUCKET should be just the bucket name in lowercase (e.g. book-promo-studio).")
    return tips


HINTS = {
    "Unauthorized": "R2 rejected the keys. Check: (1) R2_ACCOUNT_ID is the Account ID from the R2 overview page, "
                    "not a website's Zone ID (both are 32 characters); (2) the keys are the token's 'Access Key ID' "
                    "and 'Secret Access Key', not the 'Token value'; (3) the token has Object Read & Write on this "
                    "bucket.",
    "InvalidAccessKeyId": "The Access Key ID is not recognised - copy it again from the R2 API token screen.",
    "SignatureDoesNotMatch": "The Secret Access Key doesn't match the Access Key ID - copy both again.",
    "AccessDenied": "The token doesn't have permission for this bucket - give it 'Object Read & Write' and include "
                    "this bucket.",
    "NoSuchBucket": "No bucket with that name in this account - check R2_BUCKET (or, for an EU bucket, set "
                    "R2_ENDPOINT to https://<account-id>.eu.r2.cloudflarestorage.com).",
}


def explain(error: str) -> str:
    return next((h for code, h in HINTS.items() if code in error), "")


def test_connection() -> tuple[bool, str]:
    try:
        try:
            client().list_objects_v2(Bucket=_bucket(), MaxKeys=1)
        except Exception as e:
            if not _try_eu_endpoint(e):
                raise
        eu = " (EU jurisdiction)" if _found_endpoint["url"] else ""
        return True, f"Connected to bucket '{_bucket()}'{eu}."
    except Exception as e:
        msg = f"{type(e).__name__}: {str(e)[:200]}"
        return False, msg + (f" - {explain(msg)}" if explain(msg) else "")


# ---- paths --------------------------------------------------------------------------------

def rel(path: Path) -> str:
    return Path(path).resolve().relative_to(config.DATA.resolve()).as_posix()


def _key(r: str) -> str:
    return f"{config.R2_PREFIX.strip('/')}/{r}" if config.R2_PREFIX.strip("/") else r


def _skip(r: str) -> bool:
    name = r.rsplit("/", 1)[-1]
    return (r.startswith(SKIP_DIRS) or name in SKIP_NAMES or name.endswith(SKIP_SUFFIXES)
            or name.startswith("seg_") or (r.startswith("projects/") and name.endswith(".jpg")))


def _local_files() -> dict[str, list]:
    out = {}
    for root, _, files in os.walk(config.DATA):
        for f in files:
            p = Path(root) / f
            r = rel(p)
            if _skip(r):
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            out[r] = [st.st_size, round(st.st_mtime, 3)]
    return out


def _load_index() -> dict:
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_index(idx: dict) -> None:
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx), encoding="utf-8")
    tmp.replace(INDEX)


# ---- restore (start-up) -------------------------------------------------------------------------

def _remote_objects() -> dict[str, dict]:
    prefix = _key("")
    out, token = {}, None
    while True:
        kw = {"Bucket": _bucket(), "Prefix": prefix}
        if token:
            kw["ContinuationToken"] = token
        resp = client().list_objects_v2(**kw)
        for o in resp.get("Contents", []):
            r = o["Key"][len(prefix):]
            if r and not _skip(r):
                out[r] = {"size": o["Size"], "mtime": o["LastModified"].timestamp()}
        if not resp.get("IsTruncated"):
            return out
        token = resp.get("NextContinuationToken")


def restore(progress=lambda msg: None) -> dict:
    """Bring this machine up to date with the cloud copy. Never deletes local files."""
    try:
        remote = _remote_objects()
    except Exception as e:
        if not _try_eu_endpoint(e):
            raise
        remote = _remote_objects()
    idx = _load_index()
    got = kept = lazy = 0
    for r, o in remote.items():
        p = config.DATA / r
        if LAZY.match(r) and not p.exists():
            lazy += 1
            continue
        if p.exists():
            st = p.stat()
            if st.st_size == o["size"] or st.st_mtime >= o["mtime"]:
                if st.st_size == o["size"]:
                    idx[r] = [st.st_size, round(st.st_mtime, 3)]
                kept += 1
                continue
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".part")
        client().download_file(_bucket(), _key(r), str(tmp))
        tmp.replace(p)
        os.utime(p, (o["mtime"], o["mtime"]))
        st = p.stat()
        idx[r] = [st.st_size, round(st.st_mtime, 3)]
        got += 1
        if got % 20 == 0:
            progress(f"Restored {got} files...")
    _save_index(idx)
    MARKER.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    state["restored"] = True
    state["restore"] = {"downloaded": got, "already_here": kept, "videos_in_cloud": lazy,
                        "at": datetime.now().isoformat(timespec="seconds")}
    return state["restore"]


# ---- upload (after every change) ------------------------------------------------------------------

def sync_up() -> dict:
    """Upload new/changed files and delete remote copies of files removed here. Returns counts."""
    if not enabled():
        return {}
    if not (state["restored"] or MARKER.exists()):  # never overwrite the cloud from an empty, unrestored server
        raise RuntimeError("Not synced yet: the cloud copy has not been restored on this server.")
    files, idx = _local_files(), _load_index()
    up = de = 0
    for r, sig in files.items():
        if idx.get(r) == sig:
            continue
        ctype = mimetypes.guess_type(r)[0] or "application/octet-stream"
        client().upload_file(str(config.DATA / r), _bucket(), _key(r), ExtraArgs={"ContentType": ctype})
        idx[r] = sig
        up += 1
    for r in [r for r in idx if r not in files]:
        client().delete_object(Bucket=_bucket(), Key=_key(r))
        idx.pop(r)
        de += 1
    _save_index(idx)
    state["last_sync"] = datetime.now().isoformat(timespec="seconds")
    state["last_error"] = None
    state["uploaded"] += up
    state["deleted"] += de
    return {"uploaded": up, "deleted": de}


def sync_soon() -> None:
    """Start a background sync (coalesces repeated calls). Safe to call after every page run."""
    if not enabled() or not (state["restored"] or MARKER.exists()):
        return
    with _lock:
        if state["running"]:
            state["again"] = True
            return
        state["running"] = True
    threading.Thread(target=_sync_loop, daemon=True).start()


def _sync_loop() -> None:
    while True:
        try:
            sync_up()
        except Exception as e:
            state["last_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        with _lock:
            if state["again"]:
                state["again"] = False
                continue
            state["running"] = False
            return


# ---- videos kept in the cloud ------------------------------------------------------------------------

def remote_url(path: Path, download_name: str | None = None, expires: int = 3600) -> str | None:
    """Temporary private link to a file that lives only in R2 (e.g. an older rendered video)."""
    if not enabled():
        return None
    params = {"Bucket": _bucket(), "Key": _key(rel(path))}
    if download_name:
        params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
    return client().generate_presigned_url("get_object", Params=params, ExpiresIn=expires)


def in_cloud(path: Path) -> bool:
    if not enabled():
        return False
    try:
        client().head_object(Bucket=_bucket(), Key=_key(rel(path)))
        return True
    except Exception:
        return False


def fetch(path: Path) -> bool:
    """Download one cloud-only file (used before zipping a backup with videos)."""
    if Path(path).exists():
        return True
    if not enabled():
        return False
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        client().download_file(_bucket(), _key(rel(path)), str(path))
        return True
    except Exception:
        return False


# ---- backup zip (works without R2 too) ----------------------------------------------------------------

def backup_zip(book_id: str, include_videos: bool = True) -> bytes:
    roots = [config.BOOKS_DIR / book_id, config.PROJECTS_DIR / book_id]
    if include_videos:  # bring cloud-only videos down first so the backup is complete
        for rj in (config.PROJECTS_DIR / book_id).glob("*/render.json"):
            fetch(rj.parent / "final.mp4")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("backup.json", json.dumps({"app": "book-promo-studio", "book": book_id,
                                              "created": datetime.now(timezone.utc).isoformat()}))
        for root in roots:
            for p in sorted(root.rglob("*")) if root.exists() else []:
                if not p.is_file():
                    continue
                r = rel(p)
                if _skip(r) or (not include_videos and p.suffix.lower() == ".mp4" and r.startswith("projects/")):
                    continue
                z.write(p, r, compress_type=zipfile.ZIP_STORED if p.suffix.lower() in (".mp4", ".png", ".jpg",
                                                                                          ".jpeg", ".wav")
                        else zipfile.ZIP_DEFLATED)
    return buf.getvalue()


SAFE_ENTRY = re.compile(r"^(books|projects)/([a-z0-9-]{1,60})/[^\\:*?\"<>|]+$")


def restore_zip(data: bytes) -> str:
    """Unpack a backup made by backup_zip. Returns the book id. Only book/project files are accepted."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        meta = json.loads(z.read("backup.json")) if "backup.json" in z.namelist() else {}
        book_ids = set()
        entries = []
        for info in z.infolist():
            name = info.filename
            if info.is_dir() or name == "backup.json":
                continue
            m = SAFE_ENTRY.match(name)
            if not m or ".." in name.split("/"):
                raise ValueError(f"Not a Book Promo Studio backup (unexpected file: {name[:80]})")
            book_ids.add(m.group(2))
            entries.append(info)
        if len(book_ids) != 1:
            raise ValueError("A backup must contain exactly one book.")
        book_id = book_ids.pop()
        if meta.get("book") and meta["book"] != book_id:
            raise ValueError("Backup contents don't match its label.")
        if not (config.DATA / "books" / book_id / "book.json").exists() and \
                "books/" + book_id + "/book.json" not in {e.filename for e in entries}:
            raise ValueError("This backup has no book.json.")
        for info in entries:
            target = (config.DATA / info.filename).resolve()
            if config.DATA.resolve() not in target.parents:
                raise ValueError("Unsafe path in backup.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
    return book_id


def status() -> dict:
    """What the Backup & storage panel shows."""
    out = dict(state)
    out["enabled"] = enabled()
    out["bucket"] = _bucket()
    out["local_files"] = len(_local_files())
    out["local_mb"] = round(sum(v[0] for v in _local_files().values()) / 1e6, 1)
    return out


def cloud_usage() -> dict:
    objs = _remote_objects()
    return {"files": len(objs), "mb": round(sum(o["size"] for o in objs.values()) / 1e6, 1)}

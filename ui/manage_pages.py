"""Backup & storage page: cloud sync status, cloud backups (no upload needed), download / restore a .zip."""
import time

import streamlit as st

from promo import storage

from . import theme as t
from .common import WEB, current_book, run_safely


def backup_page() -> None:
    t.header("Library", "Backup & storage",
             "Keep your books, scripts and videos safe - automatically in the cloud, and as backups you can "
             "restore any time.")
    b = current_book()
    s = storage.status()

    # ---- cloud sync --------------------------------------------------------------------------------
    with st.container(border=True):
        st.markdown("#### ☁️ Cloud storage")
        if s["enabled"]:
            st.success(f"On - everything is saved to your Cloudflare R2 bucket **{s['bucket']}** and comes back "
                       "automatically when the app wakes up.")
            r = s.get("restore") or {}
            t.stats([("On this server", f"{s['local_files']} files", f"{s['local_mb']} MB"),
                     ("Last saved", (s.get("last_sync") or r.get("at") or "-")[11:19] or "-",
                      f"{s['uploaded']} uploaded · {s['deleted']} removed this session"),
                     ("Restored at start", str(r.get("downloaded", 0)), f"{r.get('videos_in_cloud', 0)} videos in cloud")])
            if s.get("last_error"):
                st.error(f"Last sync failed: {s['last_error']}")
            tips = storage.diagnose()
            if tips:
                st.warning("Your R2 settings look off:  \n" + "  \n".join(f"• {x}" for x in tips))
            c1, c2, c3 = st.columns(3)
            if c1.button("🔄 Save to cloud now", type="primary", width="stretch"):
                with st.spinner("Uploading changes..."):
                    res = run_safely(storage.sync_up)
                if res is not None:
                    st.success(f"Up to date: {res['uploaded']} uploaded, {res['deleted']} removed.")
            if c2.button("🔌 Test connection", width="stretch"):
                with st.spinner("Connecting to R2..."):
                    ok, msg = storage.test_connection()
                (st.success if ok else st.error)(msg)
            if c3.button("📊 Cloud usage", width="stretch"):
                u = run_safely(storage.cloud_usage)
                if u:
                    st.info(f"{u['files']} files · {u['mb']} MB of the 10 GB free tier ({u['mb'] / 100:.1f}%)")
        else:
            st.warning("Off. " + ("On the web version your books, scripts and videos are deleted whenever the app "
                                  "restarts." if WEB else "Your data is saved on this PC only."))
            st.markdown("**Turn it on (Cloudflare R2, free up to 10 GB):**\n"
                        "1. Cloudflare dashboard → **R2** → **Create bucket** (e.g. `book-promo-studio`).\n"
                        "2. R2 → **Manage API tokens** → **Create API token** → **Object Read & Write**, limited to "
                        "that bucket. Copy the **Access Key ID** and **Secret Access Key** (not the 'Token value').\n"
                        "3. Add these to the app's **Secrets** (web) or `.env` (PC), then restart the app:")
            st.code('R2_ACCOUNT_ID = "your account id"\nR2_ACCESS_KEY_ID = "..."\nR2_SECRET_ACCESS_KEY = "..."\n'
                    'R2_BUCKET = "book-promo-studio"', language="toml")

    left, right = st.columns(2, gap="large")

    # ---- make a backup ------------------------------------------------------------------------------
    with left, st.container(border=True):
        st.markdown("#### 📦 Back up a book")
        if not b:
            st.caption("Create a book first.")
        else:
            st.caption(f"**{b['title']}**: the book, manuscript, cover, characters, scripts, AI shots and "
                       "(optionally) videos, in one .zip.")
            include = st.toggle("Include videos", True, key="bk_videos")
            c1, c2 = st.columns(2)
            if s["enabled"] and c1.button("☁️ Save backup to cloud", type="primary", width="stretch"):
                with st.status("Saving a backup to the cloud...", expanded=True) as stt:
                    stt.write("Packing the book...")
                    name = run_safely(storage.save_backup_to_cloud, b["id"], include)
                    if name:
                        stt.update(label=f"Backup saved: {name}", state="complete")
                    else:
                        stt.update(label="Backup failed", state="error")
            if c2.button("💻 Make a .zip to download", width="stretch"):
                with st.spinner("Packing..."):
                    data = run_safely(storage.backup_zip, b["id"], include)
                if data:
                    st.session_state["_backup"] = (b["id"], data)
            ready = st.session_state.get("_backup")
            if ready and ready[0] == b["id"]:
                st.download_button(f"⬇ Download backup ({len(ready[1]) / 1e6:.1f} MB)", ready[1], type="primary",
                                   file_name=f"{b['id']}-backup-{time.strftime('%Y-%m-%d')}.zip",
                                   mime="application/zip", width="stretch")

    # ---- restore ------------------------------------------------------------------------------------
    with right, st.container(border=True):
        st.markdown("#### ♻️ Restore")
        if s["enabled"]:
            backups = run_safely(storage.list_cloud_backups) or []
            if backups:
                pick = st.selectbox("From a cloud backup (no upload needed)", range(len(backups)),
                                    format_func=lambda i: f"{backups[i]['name']}  ·  {backups[i]['mb']} MB")
                c1, c2 = st.columns([3, 1])
                if c1.button("Restore this backup", type="primary", width="stretch", key="restore_cloud"):
                    _restore(lambda: storage.restore_cloud_backup(backups[pick]["name"]), "Downloading the backup...")
                if c2.button("🗑", help="Delete this backup", width="stretch"):
                    run_safely(storage.delete_cloud_backup, backups[pick]["name"])
                    st.rerun()
            else:
                st.caption("No cloud backups yet - make one on the left.")
            st.divider()
        up = st.file_uploader("From a .zip file on your computer", ["zip"], key="restore_zip",
                              help="Big backups with videos can take a minute to upload - wait for the file name to "
                                   "appear with its size before clicking Restore.")
        if up is not None:
            st.caption(f"📎 {up.name} · {up.size / 1e6:.1f} MB received - ready to restore.")
            if st.button("Restore this file", type="primary", width="stretch", key="restore_file"):
                _restore(lambda: storage.restore_zip(up.getvalue()), "Checking the file...")


def _restore(fn, first_step: str) -> None:
    with st.status("Restoring...", expanded=True) as stt:
        stt.write(first_step)
        try:
            bid = fn()
        except Exception as e:
            stt.update(label=f"Restore failed: {e}", state="error")
            return
        stt.write(f"Unpacked the book '{bid}'.")
        if storage.enabled():
            stt.write("Saving to cloud storage...")
            run_safely(storage.sync_up)
        stt.update(label="Restored - switching to the book...", state="complete")
    st.session_state["_goto_book"] = bid
    st.session_state.pop("_backup", None)
    time.sleep(1)
    st.rerun()

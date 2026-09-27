# Book Promo Studio

Makes realistic, faceless TikTok / Reels / Shorts videos that sell your book:
**hook → feeling → proof from your real pages → soft breadcrumb (cover + where to buy).**

## Start
1. Double-click `setup.bat` (first time only).
2. Double-click `run.bat`. The app opens in your browser.
3. In the sidebar, click **⚙️ Settings & API keys**. Paste your xAI key (and OpenAI if you use it), plus a free Pexels key from pexels.com/api for free stock footage.

## Steps in the app
The steps are in the top bar. The **Studio** page shows a checklist of what's done and a button for the next step, and every page ends with a link to the next step.

| Page | What you do |
|---|---|
| 🏠 Studio | Dashboard: your book, progress checklist, latest videos, spend. |
| 1 Book | Title, **genre** (fiction, self-help, poetry, gift, medical, engineering, children's), cover, manuscript (PDF/DOCX/TXT), desk photo, your own clips. Click **Read my manuscript**, then tick the best lines to feature. |
| 2 Characters | Add the **characters** to show, with a photo or an AI portrait so the face stays the same. |
| 3 Pages | Browse the manuscript page by page and feature **pages and lines**. The video turns the pages, highlights the line and zooms in. |
| 4 Format | Optional: paste a viral book video link. The app copies its structure, never its words. |
| 5 Scripts | Choose the format, visual mix (Free only / Balanced / Cinematic), characters and pages. The AI writes several scripts, each shown as a colour-coded scene timeline, and you can edit every scene. |
| 6 Render | Pick the voice, music, captions and AI quality check, see the cost, then click **Render**. This takes about 3-5 minutes on this PC and runs in the background. |
| 7 Videos | Gallery: download, copy the caption and hashtags, log views, mark a **winner** and clone it with one thing changed. |

## Scene types
- `page`: the previous page turns, then the quote is highlighted while the camera pushes in. **Free.**
- `flip`: several pages flip past, landing on the quote. **Free.**
- `cover`: your book drops onto the desk with a light glint. **Free.** Always the last scene.
- `stock`: real stock footage from Pexels. **Free.**
- `broll`: your own uploaded clips. **Free.**
- `character` / `ai_image`: photorealistic AI photo with a slow camera move. About $0.015.
- `ai_video`: photorealistic AI video (Grok Imagine). About $0.07 per second, so use it for the hook only.

## AI quality check (on by default)
- **As each AI shot is made:** a vision AI checks every AI photo, and 4 frames of every AI clip. It looks for warped hands or faces, garbled text or logos, melting objects, a character who doesn't match their reference photo, and shots that don't match the script. If a shot scores below 7/10, it is re-made with a corrected prompt: photos up to 2 times, video clips up to the number you choose on the Render tab. The best take is kept.
- **After the scenes are drawn:** it looks through one frame of every scene in the finished video. Any AI or stock scene that still looks wrong is re-made, and only that scene is re-drawn before the final MP4 is built.
- **Cost:** each check costs about $0.001-0.005, and results are saved so a re-render never pays twice. Under each video, the **My videos** tab shows every score and what was fixed.

## Budget ($20/month)
Every paid call is checked against `MONTHLY_BUDGET_USD` first. If the next call would go over the budget, it is blocked.
- A typical video with one 4-second AI clip costs about $0.30-0.40.
- A video using only free visuals costs about $0.01 (just the voice).

You can see all spending in the sidebar under **Spending log**.

## Music
Add royalty-free tracks on the Render tab, or put them in `data/music/`. Trending TikTok sounds are best added inside the TikTok app when you post.

## Put it on the web (Streamlit Community Cloud, free)
1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app**, then **Deploy a public app from GitHub**. Pick repo `Bolakale09/book-promo-studio`, branch `main`, file `app.py`.
3. Open **Advanced settings**. Set Python to 3.12 and paste your secrets (see `.streamlit/secrets.toml.example`). `APP_PASSWORD` is required, so strangers can't spend your credits.
4. Click **Deploy**. The first build takes about 5-10 minutes.

## Cloud storage (Cloudflare R2) - keeps your work when the web app restarts
The free web server wipes its disk whenever the app sleeps or restarts. With R2 turned on, the app:
- **restores** your books, manuscripts, characters, scripts, AI shots and spending log when it wakes up;
- **saves** every change in the background, and each finished render right away;
- **streams** older videos straight from R2, so waking up stays fast.

To set it up:
1. In the Cloudflare dashboard, go to **R2** → **Create bucket**, for example `book-promo-studio`.
2. Go to R2 → **Manage API tokens** → **Create API token**. Give it **Object Read & Write** permission, limited to that bucket, and copy the Access Key ID and Secret Access Key.
3. Add `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` and `R2_BUCKET` to the app's **Secrets** (web) or to `.env` (PC), then restart the app.

If the web app and the PC use the same bucket, they share one library.

**💾 Backup & storage** in the sidebar shows the sync status. From there you can also download any book (with its videos) as a .zip and restore it later, which works even without R2.

Things to know about the web version:
- Without R2 (above), files on the free server are wiped when the app restarts. That includes books, videos and the spending log.
- Set hard monthly limits in your OpenAI and xAI billing pages too, as a second safety net.
- The free server has little CPU, so renders are slower than on your PC.

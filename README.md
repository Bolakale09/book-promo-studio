# Book Promo Studio

Makes realistic, faceless TikTok / Reels / Shorts videos that sell your book:
**hook → feeling → proof from your real pages → soft breadcrumb (cover + where to buy).**

## Start
1. Double-click `setup.bat` (first time only).
2. Double-click `run.bat`. The app opens in your browser.
3. In the sidebar, open **Settings & API keys**. Paste your OpenAI and xAI keys, and optionally a free Pexels key from pexels.com/api for free stock footage.

## Steps in the app
| Tab | What you do |
|---|---|
| 1 · Book | Title, **genre** (fiction, self-help, poetry, gift, medical, engineering, children's), cover, manuscript (PDF/DOCX/TXT). Click **Read my manuscript** so the AI finds your best lines. |
| 2 · Characters & pages | Add the **characters** to show (with a photo, or an AI portrait so the face stays the same). Pick the **pages and lines** to show. The video turns the pages, highlights the line and zooms in. |
| 3 · Viral format | Optional: paste a viral book video link. The app copies its structure, never its words. |
| 4 · Scripts | Choose the format, the characters and pages to feature, and how many AI shots. The AI writes several different scripts, and you can edit every scene. |
| 5 · Render | Pick a voice, captions and music, check the cost estimate, then click **Render**. This takes about 3-5 minutes on this PC. |
| 6 · My videos | Download, copy the caption and hashtags, log views, mark a **winner** and clone it with one thing changed. |

## Scene types
- `page`: the previous page turns, then the quote is highlighted while the camera pushes in. **Free.**
- `flip`: several pages flip past, landing on the quote. **Free.**
- `cover`: your book drops onto the desk with a light glint. **Free.** Always the last scene.
- `stock`: real stock footage from Pexels. **Free.**
- `broll`: your own uploaded clips. **Free.**
- `character` / `ai_image`: photorealistic AI photo with a slow camera move. About $0.015.
- `ai_video`: photorealistic AI video (Grok Imagine). About $0.07 per second, so use it for the hook only.

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

Things to know about the web version:
- Files on the free server are wiped when the app restarts. That includes books, videos and the spending log. **Download your videos** after rendering.
- Set hard monthly limits in your OpenAI and xAI billing pages too, because the in-app budget log resets whenever the app restarts.
- The free server has little CPU, so renders are slower than on your PC.

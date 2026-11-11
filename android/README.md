# Book Promo Studio for Android

A native Android app for your studio: a phone-sized home screen, bottom tabs, a sign-in screen, uploads from the phone, downloads into **Downloads**, microphone recording for "My own voice", and full-screen video.

The heavy work (AI calls, FFmpeg rendering, your library) still runs on your **studio server**: the Streamlit Community Cloud app or your PC. A phone can't run FFmpeg renders and faster-whisper well, and your API keys stay on the server, not on the phone.

## Get the APK
Every push to `main` that changes `android/` builds the app on GitHub (about 5-8 minutes).

- **Easiest:** open `https://github.com/Bolakale09/book-promo-studio/releases/latest` on the phone and tap **BookPromoStudio.apk**.
- Or: GitHub → **Actions** → **Android APK** → the latest run → **Artifacts**.

To install it, allow "Install unknown apps" for your browser or Files app when Android asks.

## First start
1. Type your studio address:
   - web: your `https://<name>.streamlit.app` link;
   - PC: start `run.bat` and type the **Network URL** it prints, e.g. `192.168.1.20:8501` (phone on the same Wi-Fi).
2. Type your `APP_PASSWORD` if the studio has one. You only do this once.

Use the **⋮** menu to change the address later. The **sliders** button opens the studio's sidebar (switch book, budget, Settings & API keys, Backup).

## Updates install over the old app: add the signing key once
Without a signing key, each build is signed with a new temporary key, and Android asks you to uninstall the old app first.

A release key was created for you outside the repo, in `C:\Users\Bolakale\BookPromoStudio-signing\`. Open `github-secrets.txt` there and add the 4 values at GitHub → repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | the long text |
| `ANDROID_KEYSTORE_PASSWORD` | the password |
| `ANDROID_KEY_PASSWORD` | the same password |
| `ANDROID_KEY_ALIAS` | `bookpromo` |

Then run the workflow again (Actions → Android APK → **Run workflow**). Uninstall the build you installed before the secrets were added; every build after that installs as an update. **Back up that folder**: without it, you can't update the installed app.

## Develop
Open the `android/` folder in Android Studio (Ladybug or newer). Command line: `gradle -p android assembleRelease` (Gradle 8.11, JDK 17).

How it fits together:
- `StudioWeb.kt`: the WebView and the native bridge. Page changes use Streamlit's own history event, so the sign-in and chosen book are kept.
- `StudioScreen.kt`: top bar, bottom tabs, page sheets, loading and offline screens.
- `ConnectScreen.kt`: the first-start screen.
- The web app detects the app from its User-Agent (`BookPromoStudioApp`, see `ui/theme.py`). It then hides its own top menu, and `app.py` accepts the `bps_token` cookie in place of the password form.

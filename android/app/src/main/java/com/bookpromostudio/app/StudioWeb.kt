package com.bookpromostudio.app

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.Message
import android.view.View
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.toArgb
import org.json.JSONArray
import org.json.JSONObject

/** The web app's marker: ui/theme.py looks for it to switch to the in-app layout. */
const val APP_UA = "BookPromoStudioApp/1"

/**
 * Owns the one WebView that shows the studio, and everything native around it: page switching without
 * losing the session, file uploads, downloads, the microphone, full-screen video and outside links.
 */
@SuppressLint("SetJavaScriptEnabled")
class StudioWeb(private val act: MainActivity) {
    var path by mutableStateOf("")            // current page, as a url_path ("" = Studio)
    var progress by mutableIntStateOf(0)
    var ready by mutableStateOf(false)        // the studio has drawn its first screen
    var error by mutableStateOf<String?>(null)
    var canGoBack by mutableStateOf(false)
    var fullscreen by mutableStateOf<View?>(null)
    var loadedUrl: String? = null
        private set

    private var token: String? = null
    private var host = ""
    private var loadGen = 0
    private var customViewCallback: WebChromeClient.CustomViewCallback? = null
    private val main = Handler(Looper.getMainLooper())
    private val hookJs = HOOK_JS.replace("__KNOWN__", JSONArray(Tab.allPaths).toString())

    val view: WebView = WebView(act).apply {
        setBackgroundColor(Bg.toArgb())
        overScrollMode = View.OVER_SCROLL_NEVER
        settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            setSupportMultipleWindows(true)
            javaScriptCanOpenWindowsAutomatically = true
            builtInZoomControls = false
            displayZoomControls = false
            userAgentString = "$userAgentString $APP_UA"
        }
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
        addJavascriptInterface(Bridge(), "BPSApp")
        webViewClient = Client()
        webChromeClient = Chrome()
        setDownloadListener { url, ua, cd, mime, _ -> download(url, ua, cd, mime) }
    }

    fun load(url: String, token: String?) {
        this.token = token
        loadedUrl = url
        host = Uri.parse(url).host.orEmpty()
        val cookies = CookieManager.getInstance()
        val secure = if (url.startsWith("https")) "; Secure" else ""
        cookies.setCookie(
            url,
            if (token != null) "bps_token=$token; Path=/; Max-Age=31536000$secure" else "bps_token=; Path=/; Max-Age=0",
        )
        cookies.flush()
        error = null
        ready = false
        path = ""
        view.loadUrl(url)
    }

    fun retry() {
        loadedUrl?.let { load(it, token) }
    }

    fun reload() {
        error = null
        ready = false
        view.reload()
    }

    /** Switch page inside the running app (keeps the sign-in and the chosen book). */
    fun go(target: String) {
        if (target == path && ready) return
        path = target
        view.evaluateJavascript("window.__bpsGo ? window.__bpsGo(${JSONObject.quote(target)}) : false") { r ->
            if (r != "true") loadedUrl?.let { view.loadUrl(it + target) }
        }
    }

    /** The web app's sidebar holds the book switcher, budget, settings & API keys. */
    fun toggleSidebar() {
        view.evaluateJavascript("window.__bpsSidebar ? window.__bpsSidebar() : false") { r ->
            if (r != "true") toast("The studio is still opening - try again in a moment.")
        }
    }

    fun exitFullscreen() {
        fullscreen = null
        customViewCallback?.onCustomViewHidden()
        customViewCallback = null
    }

    fun isOurs(u: Uri?): Boolean {
        if (u == null) return false
        val h = u.host ?: return false
        if (u.scheme != "http" && u.scheme != "https") return false
        return h == host || h == "streamlit.app" || h.endsWith(".streamlit.app") || h.endsWith("streamlit.io")
    }

    private fun openExternal(u: Uri) {
        try {
            act.startActivity(Intent(Intent.ACTION_VIEW, u).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: ActivityNotFoundException) {
            toast("No app can open this link.")
        }
    }

    private fun download(url: String, ua: String?, cd: String?, mime: String?) {
        val name = Downloads.fileName(url, cd, mime)
        when {
            url.startsWith("data:") -> Downloads.saveDataUrl(act, url, name)
            url.startsWith("blob:") -> view.evaluateJavascript(
                BLOB_JS.replace("__URL__", JSONObject.quote(url)).replace("__NAME__", JSONObject.quote(name)), null,
            )
            else -> Downloads.enqueue(act, url, ua, cd, mime)
        }
    }

    private fun toast(msg: String) = Toast.makeText(act, msg, Toast.LENGTH_SHORT).show()

    private inner class Client : WebViewClient() {
        override fun shouldOverrideUrlLoading(v: WebView, req: WebResourceRequest): Boolean {
            if (!req.isForMainFrame || isOurs(req.url)) return false
            openExternal(req.url)
            return true
        }

        override fun onPageStarted(v: WebView, url: String?, favicon: Bitmap?) {
            loadGen++
            error = null
            ready = false
        }

        override fun onPageFinished(v: WebView, url: String?) {
            v.evaluateJavascript(hookJs, null)
            canGoBack = v.canGoBack()
            val gen = loadGen
            // A sleeping free server shows its own "wake up" page, which never reports ready - show it anyway.
            main.postDelayed({ if (gen == loadGen && error == null) ready = true }, 9000)
        }

        override fun doUpdateVisitedHistory(v: WebView, url: String?, isReload: Boolean) {
            canGoBack = v.canGoBack()
        }

        override fun onReceivedError(v: WebView, req: WebResourceRequest, err: WebResourceError) {
            if (req.isForMainFrame) error = err.description?.toString()?.ifBlank { null } ?: "Network error"
        }
    }

    private inner class Chrome : WebChromeClient() {
        override fun onProgressChanged(v: WebView, newProgress: Int) {
            progress = newProgress
        }

        override fun onShowFileChooser(
            v: WebView, callback: ValueCallback<Array<Uri>>, params: WebChromeClient.FileChooserParams,
        ): Boolean {
            act.openFiles(callback, params)
            return true
        }

        override fun onPermissionRequest(req: PermissionRequest) {
            main.post {
                val wantsMic = PermissionRequest.RESOURCE_AUDIO_CAPTURE in req.resources
                if (wantsMic && isOurs(req.origin)) act.requestMic(req) else req.deny()
            }
        }

        override fun onShowCustomView(v: View, callback: WebChromeClient.CustomViewCallback) {
            if (fullscreen != null) {
                callback.onCustomViewHidden()
                return
            }
            fullscreen = v
            customViewCallback = callback
        }

        override fun onHideCustomView() = exitFullscreen()

        /** Links that open a new tab: downloads are saved, pages open in the phone's browser. */
        override fun onCreateWindow(v: WebView, isDialog: Boolean, isUserGesture: Boolean, msg: Message): Boolean {
            val popup = WebView(act)
            var handled = false
            fun done(w: WebView) = main.post { w.destroy() }
            popup.webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(w: WebView, r: WebResourceRequest): Boolean {
                    if (handled) return true
                    if (isOurs(r.url)) return false  // let it load: a file download arrives in the listener below
                    handled = true
                    openExternal(r.url)
                    done(w)
                    return true
                }

                override fun onPageFinished(w: WebView, url: String?) {
                    if (handled || url == null || url == "about:blank") return
                    handled = true
                    openExternal(Uri.parse(url))
                    done(w)
                }
            }
            popup.setDownloadListener { url, ua, cd, mime, _ ->
                handled = true
                download(url, ua, cd, mime)
                done(popup)
            }
            (msg.obj as WebView.WebViewTransport).webView = popup
            msg.sendToTarget()
            return true
        }
    }

    /** Called from the page's JavaScript (on a background thread). */
    private inner class Bridge {
        @JavascriptInterface
        fun onRoute(pathname: String) {
            main.post {
                path = Tab.pathOf(pathname)
                canGoBack = view.canGoBack()
            }
        }

        @JavascriptInterface
        fun onReady() {
            main.post { if (error == null) ready = true }
        }

        @JavascriptInterface
        fun saveDataUrl(dataUrl: String, name: String) {
            main.post { Downloads.saveDataUrl(act, dataUrl, name) }
        }

        @JavascriptInterface
        fun saveFailed(message: String) {
            main.post { toast("Couldn't save the file: $message") }
        }
    }

    companion object {
        /**
         * Runs in the top page. On Streamlit Community Cloud the app sits in a same-origin iframe, so we look
         * there too. Page changes use the same history event Streamlit's own back button uses, so the session
         * (sign-in, chosen book, running tasks) is kept.
         */
        private val HOOK_JS = """
            (function () {
              if (window.__bpsHooked) return;
              window.__bpsHooked = true;
              var KNOWN = __KNOWN__;
              function appWin() {
                try { if (document.querySelector('[data-testid="stApp"]')) return window; } catch (e) {}
                var frames = document.getElementsByTagName('iframe');
                for (var i = 0; i < frames.length; i++) {
                  try {
                    var w = frames[i].contentWindow;
                    if (w && w.document && w.document.querySelector('[data-testid="stApp"]')) return w;
                  } catch (e) {}
                }
                return null;
              }
              var last = null, ready = false;
              function tick() {
                var w = appWin();
                if (!w) return;
                if (!ready) {
                  var m = w.document.querySelector('[data-testid="stMainBlockContainer"]');
                  if (m && m.children.length) { ready = true; BPSApp.onReady(); }
                }
                var p = w.location.pathname;
                if (p !== last) { last = p; BPSApp.onRoute(p); }
              }
              setInterval(tick, 350);
              tick();
              window.__bpsGo = function (path) {
                var w = appWin();
                if (!w) return false;
                var parts = w.location.pathname.split('/');
                while (parts.length && parts[parts.length - 1] === '') parts.pop();
                if (parts.length && KNOWN.indexOf(parts[parts.length - 1]) >= 0) parts.pop();
                var target = parts.join('/') + '/' + path;
                if (target !== w.location.pathname) {
                  w.history.pushState({}, '', target);
                  w.dispatchEvent(new PopStateEvent('popstate'));
                }
                return true;
              };
              window.__bpsSidebar = function () {
                var w = appWin();
                if (!w) return false;
                var d = w.document;
                var sb = d.querySelector('[data-testid="stSidebar"]');
                var open = sb && sb.getAttribute('aria-expanded') === 'true';
                var id = open ? 'stSidebarCollapseButton' : 'stExpandSidebarButton';
                var b = d.querySelector('[data-testid="' + id + '"] button') || d.querySelector('[data-testid="' + id + '"]');
                if (b) { b.click(); return true; }
                return false;
              };
            })();
        """.trimIndent()

        private val BLOB_JS = """
            (function (u, n) {
              fetch(u).then(function (r) { return r.blob(); }).then(function (b) {
                var f = new FileReader();
                f.onload = function () { BPSApp.saveDataUrl(f.result, n); };
                f.readAsDataURL(b);
              }).catch(function (e) { BPSApp.saveFailed(String(e)); });
            })(__URL__, __NAME__);
        """.trimIndent()
    }
}

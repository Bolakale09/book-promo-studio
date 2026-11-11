package com.bookpromostudio.app

import android.content.Context
import android.net.Uri
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** Where the studio lives and the sign-in token, kept on the phone. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("studio", Context.MODE_PRIVATE)

    var url: String?
        get() = sp.getString("url", null)
        set(v) = sp.edit().putString("url", v).apply()

    /** HMAC of APP_PASSWORD - the web app accepts it as the `bps_token` cookie (see app.py). */
    var token: String?
        get() = sp.getString("token", null)
        set(v) = sp.edit().putString("token", v).apply()

    companion object {
        private val LOCAL = Regex("""^(localhost|\d{1,3}(\.\d{1,3}){3})(:\d+)?(/.*)?$""")

        /** "book-promo.streamlit.app" -> "https://book-promo.streamlit.app/", "192.168.1.5:8501" -> "http://...". */
        fun normalize(raw: String): String? {
            var s = raw.trim()
            if (s.isEmpty()) return null
            if (!s.startsWith("http://", true) && !s.startsWith("https://", true)) {
                s = (if (LOCAL.matches(s)) "http://" else "https://") + s
            }
            val uri = Uri.parse(s)
            val host = uri.host
            if (host.isNullOrBlank() || !host.contains('.') && host != "localhost") return null
            return "${uri.scheme!!.lowercase()}://${uri.encodedAuthority}/"
        }

        fun tokenFor(password: String): String {
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(password.toByteArray(Charsets.UTF_8), "HmacSHA256"))
            return mac.doFinal("book-promo-studio-app".toByteArray(Charsets.UTF_8))
                .joinToString("") { "%02x".format(it) }
        }
    }
}

package com.bookpromostudio.app

import android.app.DownloadManager
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Base64
import android.webkit.CookieManager
import android.webkit.URLUtil
import android.widget.Toast
import java.io.File

/** Saves videos, posting kits, captions and backups from the studio into the phone's Downloads folder. */
object Downloads {
    private val FILENAME_STAR = Regex("""filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)""")
    private val FILENAME = Regex("""filename\s*=\s*"?([^";]+)"?""")

    fun fileName(url: String, contentDisposition: String?, mime: String?): String {
        val cd = contentDisposition.orEmpty()
        val name = FILENAME_STAR.find(cd)?.groupValues?.get(1)?.let(Uri::decode)
            ?: FILENAME.find(cd)?.groupValues?.get(1)
            ?: runCatching { Uri.parse(url).getQueryParameter("title") }.getOrNull()  // throws for data:/blob:
            ?: URLUtil.guessFileName(url, contentDisposition, mime)
        return name.replace(Regex("""[\\/:*?"<>|]"""), "_").trim().ifEmpty { "download" }
    }

    /** An ordinary http(s) link: hand it to Android's download manager (shows progress in the notifications). */
    fun enqueue(ctx: Context, url: String, userAgent: String?, contentDisposition: String?, mime: String?) {
        val name = fileName(url, contentDisposition, mime)
        try {
            val req = DownloadManager.Request(Uri.parse(url))
                .setTitle(name)
                .setDescription("Book Promo Studio")
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            if (!mime.isNullOrBlank()) req.setMimeType(mime)
            userAgent?.let { req.addRequestHeader("User-Agent", it) }
            CookieManager.getInstance().getCookie(url)?.let { req.addRequestHeader("Cookie", it) }
            if (Build.VERSION.SDK_INT >= 29) {
                req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name)
            } else {
                req.setDestinationInExternalFilesDir(ctx, Environment.DIRECTORY_DOWNLOADS, name)
            }
            (ctx.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager).enqueue(req)
            toast(ctx, "Downloading $name")
        } catch (e: Exception) {
            toast(ctx, "Couldn't download: ${e.message}")
        }
    }

    /** A data: URL (also what the page sends us for blob: links). */
    fun saveDataUrl(ctx: Context, dataUrl: String, name: String) {
        try {
            val comma = dataUrl.indexOf(',')
            require(dataUrl.startsWith("data:") && comma > 0) { "not a data URL" }
            val meta = dataUrl.substring(5, comma)
            val mime = meta.substringBefore(';').ifBlank { "application/octet-stream" }
            val body = dataUrl.substring(comma + 1)
            val bytes = if (meta.endsWith(";base64")) Base64.decode(body, Base64.DEFAULT)
            else Uri.decode(body).toByteArray()
            saveBytes(ctx, bytes, name.ifBlank { "download" }, mime)
            toast(ctx, "Saved $name to Downloads")
        } catch (e: Exception) {
            toast(ctx, "Couldn't save the file: ${e.message}")
        }
    }

    private fun saveBytes(ctx: Context, bytes: ByteArray, name: String, mime: String) {
        if (Build.VERSION.SDK_INT >= 29) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, name)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val resolver = ctx.contentResolver
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: error("no space in Downloads")
            resolver.openOutputStream(uri)?.use { it.write(bytes) }
            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
        } else {
            val dir = ctx.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: ctx.filesDir
            File(dir, name).writeBytes(bytes)
        }
    }

    private fun toast(ctx: Context, msg: String) = Toast.makeText(ctx, msg, Toast.LENGTH_SHORT).show()
}

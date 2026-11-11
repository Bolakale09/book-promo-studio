package com.bookpromostudio.app

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.webkit.MimeTypeMap
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen

class MainActivity : ComponentActivity() {
    lateinit var prefs: Prefs
        private set
    val studio by lazy { StudioWeb(this) }

    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var pendingMic: PermissionRequest? = null

    private val filePicker = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { res ->
        val cb = fileCallback ?: return@registerForActivityResult
        fileCallback = null
        val data = res.data
        val uris: Array<Uri>? = when {
            res.resultCode != RESULT_OK || data == null -> null
            data.clipData != null -> data.clipData!!.let { c -> Array(c.itemCount) { c.getItemAt(it).uri } }
            data.data != null -> arrayOf(data.data!!)
            else -> null
        }
        cb.onReceiveValue(uris)
    }

    private val micPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        val req = pendingMic ?: return@registerForActivityResult
        pendingMic = null
        if (ok) req.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) else req.deny()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        prefs = Prefs(this)

        setContent {
            BpsTheme {
                var url by remember { mutableStateOf(prefs.url) }
                var editing by remember { mutableStateOf(prefs.url == null) }
                val current = url
                if (editing || current == null) {
                    ConnectScreen(
                        initialUrl = current.orEmpty(),
                        hasPassword = prefs.token != null,
                        onCancel = if (current != null) ({ editing = false }) else null,
                        onConnect = { newUrl, password ->
                            prefs.url = newUrl
                            // null = keep the saved password
                            if (password != null) prefs.token = Prefs.tokenFor(password)
                            url = newUrl
                            editing = false
                            studio.load(newUrl, prefs.token)
                        },
                    )
                } else {
                    LaunchedEffect(current) {
                        if (studio.loadedUrl != current) studio.load(current, prefs.token)
                    }
                    StudioScreen(studio, onChangeAddress = { editing = true })
                }
            }
        }
    }

    /** <input type=file> in the studio: manuscripts, covers, photos, clips, music, recordings, backups. */
    fun openFiles(callback: ValueCallback<Array<Uri>>, params: WebChromeClient.FileChooserParams) {
        fileCallback?.onReceiveValue(null)
        fileCallback = callback
        val accepts = params.acceptTypes.flatMap { it.split(',') }.map { it.trim().lowercase() }.filter { it.isNotEmpty() }
        val mimes = accepts.map { a ->
            if (a.startsWith(".")) MimeTypeMap.getSingleton().getMimeTypeFromExtension(a.drop(1)) else a
        }
        val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            // Only filter when every accepted type is known, so nothing the studio accepts is hidden.
            val known = mimes.filterNotNull().distinct()
            if (known.isNotEmpty() && known.size == mimes.size) {
                type = if (known.size == 1) known[0] else "*/*"
                if (known.size > 1) putExtra(Intent.EXTRA_MIME_TYPES, known.toTypedArray())
            } else {
                type = "*/*"
            }
            if (params.mode == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) {
                putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
            }
        }
        try {
            filePicker.launch(Intent.createChooser(intent, "Choose a file"))
        } catch (e: ActivityNotFoundException) {
            fileCallback = null
            callback.onReceiveValue(null)
        }
    }

    /** "My own voice": the studio asks for the microphone to record narration. */
    fun requestMic(req: PermissionRequest) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            req.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
            return
        }
        pendingMic?.deny()
        pendingMic = req
        micPermission.launch(Manifest.permission.RECORD_AUDIO)
    }

    fun versionName(): String = try {
        packageManager.getPackageInfo(packageName, 0).versionName ?: ""
    } catch (e: Exception) {
        ""
    }
}

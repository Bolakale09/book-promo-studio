package com.bookpromostudio.app

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Cloud
import androidx.compose.material.icons.rounded.Computer
import androidx.compose.material.icons.rounded.Language
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/** The app's logo: the launcher icon's open book on the coral gradient. */
@Composable
fun Logo(size: Dp) {
    val shape = RoundedCornerShape(size * 0.3f)
    Box(
        Modifier
            .size(size)
            .shadow(size / 3, shape, ambientColor = Coral, spotColor = Coral)
            .clip(shape)
            .background(BrandGradient),
        contentAlignment = Alignment.Center,
    ) {
        Image(painterResource(R.drawable.ic_launcher_foreground), null, Modifier.requiredSize(size * 1.5f))
    }
}

/** The web app's soft coral and violet glow behind the page. */
fun Modifier.glow(): Modifier = drawBehind {
    drawRect(
        Brush.radialGradient(
            listOf(Coral.copy(alpha = 0.22f), Color.Transparent),
            center = Offset(size.width * 0.1f, size.height * 0.06f),
            radius = size.width * 0.95f,
        ),
    )
    drawRect(
        Brush.radialGradient(
            listOf(Violet.copy(alpha = 0.18f), Color.Transparent),
            center = Offset(size.width * 1.0f, size.height * 0.42f),
            radius = size.width * 0.9f,
        ),
    )
}

@Composable
fun ConnectScreen(
    initialUrl: String,
    hasPassword: Boolean,
    onCancel: (() -> Unit)?,
    onConnect: (url: String, password: String?) -> Unit,
) {
    var address by rememberSaveable { mutableStateOf(initialUrl) }
    var password by rememberSaveable { mutableStateOf("") }
    var showPassword by remember { mutableStateOf(false) }
    var checking by remember { mutableStateOf(false) }
    var problem by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current

    fun submit(force: Boolean) {
        focus.clearFocus()
        val url = Prefs.normalize(address)
        if (url == null) {
            problem = "That doesn't look like a web address."
            return
        }
        val pw = password.trim().ifEmpty { null }  // keyboards often add a trailing space
        if (force) return onConnect(url, pw)
        checking = true
        problem = null
        scope.launch {
            val err = withContext(Dispatchers.IO) { reach(url) }
            checking = false
            if (err == null) onConnect(url, pw) else problem = err
        }
    }

    BackHandler(enabled = onCancel != null) { onCancel?.invoke() }

    val fieldColors = OutlinedTextFieldDefaults.colors(
        focusedBorderColor = Coral,
        unfocusedBorderColor = Line,
        focusedLabelColor = Coral2,
        cursorColor = Coral,
        focusedContainerColor = Bg.copy(alpha = 0.5f),
        unfocusedContainerColor = Bg.copy(alpha = 0.5f),
    )

    Box(Modifier.fillMaxSize().background(Bg).glow()) {
        Column(
            Modifier
                .fillMaxSize()
                .systemBarsPadding()
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 22.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Row(Modifier.fillMaxWidth().height(56.dp), verticalAlignment = Alignment.CenterVertically) {
                if (onCancel != null) {
                    IconButton(onClick = onCancel) { Icon(Icons.Rounded.Close, "Cancel") }
                }
            }
            Spacer(Modifier.height(12.dp))
            Logo(84.dp)
            Spacer(Modifier.height(22.dp))
            Text("Book Promo Studio", style = MaterialTheme.typography.headlineMedium, color = Ink)
            Spacer(Modifier.height(8.dp))
            Text(
                "Faceless TikTok, Reels and Shorts videos that sell your book.",
                style = MaterialTheme.typography.bodyLarge,
                color = Muted,
                textAlign = TextAlign.Center,
                modifier = Modifier.width(300.dp),
            )
            Spacer(Modifier.height(30.dp))

            Surface(
                shape = RoundedCornerShape(26.dp),
                color = Surface1.copy(alpha = 0.92f),
                border = BorderStroke(1.dp, Color.White.copy(alpha = 0.07f)),
                shadowElevation = 12.dp,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(Modifier.padding(20.dp)) {
                    Text("CONNECT YOUR STUDIO", style = Eyebrow)
                    Spacer(Modifier.height(14.dp))
                    OutlinedTextField(
                        value = address,
                        onValueChange = { address = it; problem = null },
                        label = { Text("Studio address") },
                        placeholder = { Text("YOUR-APP-NAME.streamlit.app") },
                        leadingIcon = { Icon(Icons.Rounded.Language, null) },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Uri,
                            imeAction = ImeAction.Next,
                            autoCorrectEnabled = false,
                        ),
                        shape = RoundedCornerShape(16.dp),
                        colors = fieldColors,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Spacer(Modifier.height(12.dp))
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("App password") },
                        placeholder = { Text(if (hasPassword) "Saved - leave blank to keep" else "If your studio has one") },
                        leadingIcon = { Icon(Icons.Rounded.Lock, null) },
                        trailingIcon = {
                            IconButton(onClick = { showPassword = !showPassword }) {
                                Icon(
                                    if (showPassword) Icons.Rounded.VisibilityOff else Icons.Rounded.Visibility,
                                    if (showPassword) "Hide password" else "Show password",
                                )
                            }
                        },
                        visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = { submit(false) }),
                        shape = RoundedCornerShape(16.dp),
                        colors = fieldColors,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Text(
                        "The APP_PASSWORD from your app's Secrets. Saved on this phone, so you sign in once.",
                        style = MaterialTheme.typography.bodySmall,
                        color = Muted,
                        modifier = Modifier.padding(start = 4.dp, top = 6.dp),
                    )
                    problem?.let { msg ->
                        Spacer(Modifier.height(12.dp))
                        Surface(
                            shape = RoundedCornerShape(14.dp),
                            color = Color(0x24E65A50),
                            border = BorderStroke(1.dp, Color(0x73E65A50)),
                        ) {
                            Column(Modifier.padding(12.dp)) {
                                Text(msg, style = MaterialTheme.typography.bodyMedium, color = Color(0xFFF4A49B))
                                TextButton(onClick = { submit(true) }, contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) {
                                    Text("Connect anyway", color = Coral2, fontWeight = FontWeight.SemiBold)
                                }
                            }
                        }
                    }
                    Spacer(Modifier.height(18.dp))
                    Button(
                        onClick = { submit(false) },
                        enabled = !checking && address.isNotBlank(),
                        shape = RoundedCornerShape(16.dp),
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                    ) {
                        if (checking) {
                            CircularProgressIndicator(Modifier.size(22.dp), color = Bg, strokeWidth = 2.5.dp)
                        } else {
                            Text("Connect", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                        }
                    }
                }
            }

            Spacer(Modifier.height(22.dp))
            Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                HelpRow(
                    Icons.Rounded.Cloud, "On the web",
                    "Your Streamlit Community Cloud link, like https://YOUR-APP-NAME.streamlit.app (find it at share.streamlit.io)",
                )
                HelpRow(
                    Icons.Rounded.Computer, "On your PC",
                    "Start run.bat and type the Network URL it shows, like 192.168.1.20:8501. Keep the phone on the same Wi-Fi.",
                )
            }
            Spacer(Modifier.height(36.dp))
        }
    }
}

@Composable
private fun HelpRow(icon: ImageVector, title: String, text: String) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(Surface1.copy(alpha = 0.6f))
            .padding(14.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Box(
            Modifier.size(36.dp).clip(RoundedCornerShape(11.dp)).background(Surface2),
            contentAlignment = Alignment.Center,
        ) { Icon(icon, null, tint = Coral2, modifier = Modifier.size(20.dp)) }
        Spacer(Modifier.width(12.dp))
        Column {
            Text(title, style = MaterialTheme.typography.titleSmall, color = Ink)
            Text(text, style = MaterialTheme.typography.bodySmall, color = Muted)
        }
    }
}

/** null if the address answers at all (even a sleeping Streamlit app answers), else a friendly message. */
private fun reach(url: String): String? = try {
    val conn = (URL(url).openConnection() as HttpURLConnection).apply {
        connectTimeout = 12_000
        readTimeout = 12_000
        instanceFollowRedirects = true
        setRequestProperty("User-Agent", APP_UA)
    }
    val code = conn.responseCode
    conn.disconnect()
    if (code == 404) "Nothing is at $url - check the spelling. Your address is in share.streamlit.io (web) or the run.bat window (PC)." else null
} catch (e: Exception) {
    "Couldn't reach $url. Check the address and that the studio is running."
}

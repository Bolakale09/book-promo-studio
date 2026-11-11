package com.bookpromostudio.app

import android.content.Intent
import android.net.Uri
import android.view.ViewGroup
import android.widget.FrameLayout
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.CloudOff
import androidx.compose.material.icons.rounded.Link
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.OpenInBrowser
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material3.BottomSheetDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import kotlinx.coroutines.delay

private fun Tab.headline() = when (this) {
    Tab.SetUp -> "Get your book ready"
    Tab.Make -> "Make a video"
    Tab.Grow -> "Post and grow"
    else -> label
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun StudioScreen(web: StudioWeb, onChangeAddress: () -> Unit) {
    val act = LocalContext.current as MainActivity
    val tab = Tab.of(web.path)
    val dest = Tab.dest(web.path)
    var sheet by remember { mutableStateOf<Tab?>(null) }
    var menu by remember { mutableStateOf(false) }
    val keyboardOpen = WindowInsets.isImeVisible

    BackHandler(enabled = web.canGoBack) { web.view.goBack() }
    BackHandler(enabled = web.fullscreen != null) { web.exitFullscreen() }

    LaunchedEffect(web.fullscreen != null) {
        val bars = WindowCompat.getInsetsController(act.window, act.window.decorView)
        if (web.fullscreen != null) {
            bars.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            bars.hide(WindowInsetsCompat.Type.systemBars())
        } else {
            bars.show(WindowInsetsCompat.Type.systemBars())
        }
    }

    Box(Modifier.fillMaxSize().background(Bg)) {
        Scaffold(
            containerColor = Bg,
            topBar = {
                Column {
                    TopAppBar(
                        navigationIcon = { Box(Modifier.padding(start = 14.dp, end = 6.dp)) { Logo(36.dp) } },
                        title = {
                            Column {
                                Text("BOOK PROMO STUDIO", style = Eyebrow)
                                Text(
                                    dest.title,
                                    style = MaterialTheme.typography.titleLarge,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                        },
                        actions = {
                            IconButton(onClick = web::toggleSidebar) {
                                Icon(Icons.Rounded.Tune, "Book, budget and settings")
                            }
                            Box {
                                IconButton(onClick = { menu = true }) { Icon(Icons.Rounded.MoreVert, "More") }
                                DropdownMenu(
                                    expanded = menu,
                                    onDismissRequest = { menu = false },
                                    containerColor = Surface2,
                                    shape = RoundedCornerShape(16.dp),
                                ) {
                                    MenuRow("Book, budget & settings", Icons.Rounded.Tune) {
                                        menu = false; web.toggleSidebar()
                                    }
                                    MenuRow("Reload", Icons.Rounded.Refresh) { menu = false; web.reload() }
                                    MenuRow("Open in browser", Icons.Rounded.OpenInBrowser) {
                                        menu = false
                                        web.loadedUrl?.let {
                                            runCatching { act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(it + web.path))) }
                                        }
                                    }
                                    MenuRow("Change studio address", Icons.Rounded.Link) { menu = false; onChangeAddress() }
                                    HorizontalDivider(color = Line, modifier = Modifier.padding(vertical = 4.dp))
                                    DropdownMenuItem(
                                        text = { Text("Version ${act.versionName()}", color = Muted) },
                                        onClick = {},
                                        enabled = false,
                                    )
                                }
                            }
                        },
                        colors = TopAppBarDefaults.topAppBarColors(
                            containerColor = Bg,
                            scrolledContainerColor = Bg,
                            titleContentColor = Ink,
                            actionIconContentColor = Ink,
                        ),
                    )
                    HorizontalDivider(color = Color.White.copy(alpha = 0.06f))
                }
            },
            bottomBar = {
                if (!keyboardOpen) {
                    Column {
                        HorizontalDivider(color = Color.White.copy(alpha = 0.06f))
                        NavigationBar(containerColor = Color(0xFF101018), tonalElevation = 0.dp) {
                            Tab.entries.forEach { t ->
                                val selected = t == tab
                                NavigationBarItem(
                                    selected = selected,
                                    onClick = { if (t.dests.size == 1) web.go(t.dests[0].path) else sheet = t },
                                    icon = { Icon(if (selected) t.selectedIcon else t.icon, null) },
                                    label = {
                                        Text(t.label, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium)
                                    },
                                    colors = NavigationBarItemDefaults.colors(
                                        selectedIconColor = Coral,
                                        selectedTextColor = Ink,
                                        indicatorColor = Coral.copy(alpha = 0.16f),
                                        unselectedIconColor = Muted,
                                        unselectedTextColor = Muted,
                                    ),
                                )
                            }
                        }
                    }
                }
            },
        ) { pad ->
            Box(
                Modifier
                    .fillMaxSize()
                    .padding(pad)
                    .consumeWindowInsets(pad)
                    .imePadding(),
            ) {
                AndroidView(
                    factory = { web.view.also { (it.parent as? ViewGroup)?.removeView(it) } },
                    modifier = Modifier.fillMaxSize(),
                )
                if (web.ready && web.progress in 1..99) {
                    LinearProgressIndicator(
                        progress = { web.progress / 100f },
                        modifier = Modifier.fillMaxWidth().height(2.dp),
                        color = Coral,
                        trackColor = Color.Transparent,
                    )
                }
                AnimatedVisibility(
                    visible = !web.ready && web.error == null,
                    enter = fadeIn(),
                    exit = fadeOut(tween(450)),
                ) { LoadingPane() }
                web.error?.let { ErrorPane(it, onRetry = web::retry, onChangeAddress = onChangeAddress) }
            }
        }

        // A video played full screen.
        web.fullscreen?.let { v ->
            key(v) {
                AndroidView(
                    factory = { c ->
                        FrameLayout(c).apply {
                            setBackgroundColor(android.graphics.Color.BLACK)
                            (v.parent as? ViewGroup)?.removeView(v)
                            addView(v, FrameLayout.LayoutParams(-1, -1))
                        }
                    },
                    modifier = Modifier.fillMaxSize(),
                )
            }
        }
    }

    sheet?.let { t ->
        ModalBottomSheet(
            onDismissRequest = { sheet = null },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = Surface1,
            dragHandle = { BottomSheetDefaults.DragHandle(color = Line) },
        ) {
            Column(Modifier.padding(horizontal = 14.dp).padding(bottom = 18.dp).navigationBarsPadding()) {
                Text(t.label.uppercase(), style = Eyebrow, modifier = Modifier.padding(start = 10.dp))
                Text(
                    t.headline(),
                    style = MaterialTheme.typography.headlineSmall,
                    color = Ink,
                    modifier = Modifier.padding(start = 10.dp, top = 4.dp, bottom = 12.dp),
                )
                t.dests.forEach { d ->
                    DestRow(d, selected = d.path == web.path) {
                        sheet = null
                        web.go(d.path)
                    }
                }
            }
        }
    }
}

@Composable
private fun MenuRow(text: String, icon: androidx.compose.ui.graphics.vector.ImageVector, onClick: () -> Unit) {
    DropdownMenuItem(
        text = { Text(text, color = Ink) },
        leadingIcon = { Icon(icon, null, tint = Coral2) },
        onClick = onClick,
    )
}

@Composable
private fun DestRow(d: Dest, selected: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(20.dp),
        color = if (selected) Coral.copy(alpha = 0.10f) else Color.Transparent,
        border = if (selected) BorderStroke(1.dp, Coral.copy(alpha = 0.38f)) else null,
        modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
    ) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(46.dp)
                    .clip(RoundedCornerShape(15.dp))
                    .background(if (selected) BrandGradient else SolidColor(Surface2)),
                contentAlignment = Alignment.Center,
            ) { Icon(d.icon, null, tint = if (selected) Color.White else Coral2) }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(d.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = Ink)
                Text(d.blurb, style = MaterialTheme.typography.bodySmall, color = Muted)
            }
            Icon(Icons.Rounded.ChevronRight, null, tint = Muted)
        }
    }
}

@Composable
private fun LoadingPane() {
    var slow by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        delay(5000)
        slow = true
    }
    val pulse = rememberInfiniteTransition(label = "pulse")
    val scale by pulse.animateFloat(
        initialValue = 0.94f,
        targetValue = 1.06f,
        animationSpec = infiniteRepeatable(tween(900, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "scale",
    )
    Box(Modifier.fillMaxSize().background(Bg).glow(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(36.dp)) {
            Box(Modifier.graphicsLayer { scaleX = scale; scaleY = scale }) { Logo(76.dp) }
            Spacer(Modifier.height(28.dp))
            Text("Opening your studio...", style = MaterialTheme.typography.titleMedium, color = Ink)
            Spacer(Modifier.height(8.dp))
            AnimatedVisibility(visible = slow, enter = fadeIn()) {
                Text(
                    "Free servers sleep when nobody is using them. Waking yours can take up to a minute.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Muted,
                    textAlign = TextAlign.Center,
                )
            }
            Spacer(Modifier.height(22.dp))
            LinearProgressIndicator(
                modifier = Modifier.width(150.dp).clip(RoundedCornerShape(99.dp)),
                color = Coral,
                trackColor = Surface2,
            )
        }
    }
}

@Composable
private fun ErrorPane(message: String, onRetry: () -> Unit, onChangeAddress: () -> Unit) {
    Box(Modifier.fillMaxSize().background(Bg).glow(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(32.dp)) {
            Box(
                Modifier.size(76.dp).clip(CircleShape).background(Surface2),
                contentAlignment = Alignment.Center,
            ) { Icon(Icons.Rounded.CloudOff, null, tint = Coral2, modifier = Modifier.size(36.dp)) }
            Spacer(Modifier.height(22.dp))
            Text("Can't reach your studio", style = MaterialTheme.typography.headlineSmall, color = Ink)
            Spacer(Modifier.height(10.dp))
            Text(
                "Check your internet connection. If the studio runs on your PC, make sure it's on and the phone is on the same Wi-Fi.",
                style = MaterialTheme.typography.bodyMedium,
                color = Muted,
                textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(6.dp))
            Text(message, style = MaterialTheme.typography.bodySmall, color = Muted.copy(alpha = 0.7f), textAlign = TextAlign.Center)
            Spacer(Modifier.height(26.dp))
            Button(onClick = onRetry, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth().height(52.dp)) {
                Icon(Icons.Rounded.Refresh, null)
                Spacer(Modifier.width(8.dp))
                Text("Try again", fontWeight = FontWeight.SemiBold)
            }
            Spacer(Modifier.height(6.dp))
            TextButton(onClick = onChangeAddress) { Text("Change studio address", color = Coral2) }
        }
    }
}

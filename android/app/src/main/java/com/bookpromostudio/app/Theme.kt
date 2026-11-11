package com.bookpromostudio.app

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp

// Same palette as the web app (.streamlit/config.toml and ui/theme.py).
val Bg = Color(0xFF0B0B14)
val Surface1 = Color(0xFF14141F)
val Surface2 = Color(0xFF1C1C2A)
val Line = Color(0xFF2A2D38)
val Coral = Color(0xFFFF5A36)
val Coral2 = Color(0xFFFF9A7A)
val Pink = Color(0xFFFF3D6E)
val Violet = Color(0xFF7B5CFF)
val Ink = Color(0xFFF5F2EA)
val Muted = Color(0xFF9C978E)

val BrandGradient = Brush.linearGradient(listOf(Color(0xFFFF7A2F), Coral, Pink))

private val Scheme = darkColorScheme(
    primary = Coral,
    onPrimary = Bg,
    primaryContainer = Color(0xFF3A1A14),
    onPrimaryContainer = Coral2,
    secondary = Violet,
    onSecondary = Ink,
    background = Bg,
    onBackground = Ink,
    surface = Surface1,
    onSurface = Ink,
    surfaceVariant = Surface2,
    onSurfaceVariant = Muted,
    surfaceContainerLowest = Bg,
    surfaceContainerLow = Color(0xFF111119),
    surfaceContainer = Surface1,
    surfaceContainerHigh = Surface2,
    surfaceContainerHighest = Color(0xFF242434),
    outline = Line,
    outlineVariant = Line,
    error = Color(0xFFF4A49B),
)

private val Serif = FontFamily.Serif
private val base = Typography()
private val Type = base.copy(
    displaySmall = base.displaySmall.copy(fontFamily = Serif, fontWeight = FontWeight.Bold, letterSpacing = (-0.02).em),
    headlineMedium = base.headlineMedium.copy(fontFamily = Serif, fontWeight = FontWeight.Bold, letterSpacing = (-0.01).em),
    headlineSmall = base.headlineSmall.copy(fontFamily = Serif, fontWeight = FontWeight.Bold),
    titleLarge = base.titleLarge.copy(fontFamily = Serif, fontWeight = FontWeight.Bold),
)

val Eyebrow = TextStyle(fontSize = 10.5.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.16.em, color = Coral)

@Composable
fun BpsTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Scheme, typography = Type, content = content)
}

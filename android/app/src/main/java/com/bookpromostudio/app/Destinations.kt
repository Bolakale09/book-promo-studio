package com.bookpromostudio.app

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Book
import androidx.compose.material.icons.outlined.Dashboard
import androidx.compose.material.icons.outlined.RocketLaunch
import androidx.compose.material.icons.outlined.VideoLibrary
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.AutoStories
import androidx.compose.material.icons.rounded.Book
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.CloudSync
import androidx.compose.material.icons.rounded.Dashboard
import androidx.compose.material.icons.rounded.EditNote
import androidx.compose.material.icons.rounded.Insights
import androidx.compose.material.icons.rounded.LocalFireDepartment
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.Palette
import androidx.compose.material.icons.rounded.Repeat
import androidx.compose.material.icons.rounded.RocketLaunch
import androidx.compose.material.icons.rounded.TheaterComedy
import androidx.compose.material.icons.rounded.VideoLibrary
import androidx.compose.ui.graphics.vector.ImageVector

/** One page of the web app. `path` is its url_path in app.py ("" = the Studio home page). */
data class Dest(val path: String, val title: String, val blurb: String, val icon: ImageVector)

/** The bottom tabs. A tab with one page opens it; a tab with several opens a sheet to pick from. */
enum class Tab(val label: String, val icon: ImageVector, val selectedIcon: ImageVector, val dests: List<Dest>) {
    Studio(
        "Studio", Icons.Outlined.Dashboard, Icons.Rounded.Dashboard,
        listOf(Dest("", "Studio", "Your book, progress and latest videos", Icons.Rounded.Dashboard)),
    ),
    SetUp(
        "Set up", Icons.Outlined.Book, Icons.Rounded.Book,
        listOf(
            Dest("book", "Book", "Title, genre, cover and manuscript", Icons.Rounded.Book),
            Dest("characters", "Characters", "Who appears, with a steady face", Icons.Rounded.TheaterComedy),
            Dest("pages", "Pages", "Feature pages and lines to highlight", Icons.Rounded.AutoStories),
            Dest("viral", "Viral finder", "Find viral book videos and copy a style", Icons.Rounded.LocalFireDepartment),
            Dest("format", "Format", "Copy a video's structure, never its words", Icons.Rounded.Repeat),
            Dest("brand", "Brand kit", "Handle, logo, caption colours, hashtags", Icons.Rounded.Palette),
        ),
    ),
    Make(
        "Make", Icons.Outlined.AutoAwesome, Icons.Rounded.AutoAwesome,
        listOf(
            Dest("scripts", "Scripts", "AI writes scripts you can edit scene by scene", Icons.Rounded.EditNote),
            Dest("render", "Render", "Voice, music and captions, then make the video", Icons.Rounded.Movie),
        ),
    ),
    Videos(
        "Videos", Icons.Outlined.VideoLibrary, Icons.Rounded.VideoLibrary,
        listOf(Dest("videos", "Videos", "Download, posting kit, redo a scene", Icons.Rounded.VideoLibrary)),
    ),
    Grow(
        "Grow", Icons.Outlined.RocketLaunch, Icons.Rounded.RocketLaunch,
        listOf(
            Dest("calendar", "Calendar", "Plan posts and get reminders", Icons.Rounded.CalendarMonth),
            Dest("results", "Results", "Log views and sales, see what works", Icons.Rounded.Insights),
            Dest("backup", "Backup & storage", "Cloud sync and backups", Icons.Rounded.CloudSync),
        ),
    );

    companion object {
        val allPaths: List<String> = entries.flatMap { t -> t.dests.map { it.path } }.filter { it.isNotEmpty() }

        fun of(path: String): Tab = entries.firstOrNull { t -> t.dests.any { it.path == path } } ?: Studio

        fun dest(path: String): Dest = entries.flatMap { it.dests }.firstOrNull { it.path == path } ?: Studio.dests[0]

        /** "/~/+/book" or "/book/" -> "book"; anything that isn't a known page -> "" (Studio). */
        fun pathOf(pathname: String): String {
            val last = pathname.trimEnd('/').substringAfterLast('/')
            return if (last in allPaths) last else ""
        }
    }
}

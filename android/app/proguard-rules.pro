# The web page calls these methods by name (window.BPSApp.onRoute(...) etc.).
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

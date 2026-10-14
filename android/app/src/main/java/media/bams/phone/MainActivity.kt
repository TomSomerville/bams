package media.bams.phone

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.ConnectivityManager
import android.net.Network
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.webkit.ConsoleMessage
import android.webkit.CookieManager
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.webkit.WebViewAssetLoader
import java.io.FileInputStream
import java.net.URLConnection

/**
 * BAMS on a phone. Online it's the server's own web UI in a WebView (the same pages as in a browser, plus Download
 * buttons: web/src/android.ts). With no server in reach it opens the app's own Downloads pages (built from web/,
 * bundled as assets/app), which play what's on the phone. It looks for the server again by itself, and the
 * Downloads page offers to go back online when it answers.
 */
class MainActivity : Activity() {
    private lateinit var root: FrameLayout
    private lateinit var web: WebView
    private lateinit var bridge: Bridge
    private lateinit var music: Music
    private val app get() = application as App
    private val main = Handler(Looper.getMainLooper())
    private var fullscreen: View? = null
    private var fullscreenDone: WebChromeClient.CustomViewCallback? = null
    /** the server whose page is showing (null: the app's own pages) */
    private var current: Servers.Server? = null
    private var currentBase: String? = null
    /** name of the server that stopped answering, for the Downloads page's note */
    var lost: String? = null
        private set
    private var clearHistory = false

    private val loader by lazy {
        WebViewAssetLoader.Builder()
            .addPathHandler("/app/", WebViewAssetLoader.PathHandler { path -> asset("app/" + path.ifEmpty { "index.html" }) })
            // a download's pictures: /dl/<server id>/images/<path as the server had it>
            .addPathHandler("/dl/", WebViewAssetLoader.PathHandler { path -> picture(path) })
            .build()
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val debuggable = applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
        WebView.setWebContentsDebuggingEnabled(debuggable)  // chrome://inspect from a PC, debug builds only

        web = WebView(this).apply { setBackgroundColor(Color.parseColor("#0f1216")) }
        root = FrameLayout(this).apply { setBackgroundColor(Color.parseColor("#0f1216")) }
        root.addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(root)
        // the page stays clear of the status bar, the navigation bar and a camera cut-out (Android 15 draws edge to edge)
        root.setOnApplyWindowInsetsListener { v, insets ->
            if (fullscreen == null) {
                val bars = if (Build.VERSION.SDK_INT >= 30)
                    insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout() or WindowInsets.Type.ime())
                else null
                @Suppress("DEPRECATION")
                if (bars != null) v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
                else v.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop, insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            } else v.setPadding(0, 0, 0, 0)
            insets
        }

        CookieManager.getInstance().setAcceptCookie(true)
        with(web.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true                       // localStorage: the web UI's other servers, choices
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = false
            setSupportZoom(false)
            textZoom = 100
            userAgentString = "$userAgentString BAMS-Android/${app.version()}"
        }

        web.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                loader.shouldInterceptRequest(request.url)

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                val origin = Servers.origin(url)
                if (origin == APP_ORIGIN || origin == currentBase || app.servers.forOrigin(origin)?.shown == true) return false
                // IMDb, TMDB, Wikipedia…: the phone's browser
                try { startActivity(Intent(Intent.ACTION_VIEW, request.url)) } catch (e: Exception) {}
                return true
            }

            override fun onPageFinished(view: WebView, url: String) {
                if (clearHistory) { view.clearHistory(); clearHistory = false }
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                // the server's page itself didn't load (gone out of reach): what's on the phone instead
                if (request.isForMainFrame && current != null && Servers.origin(request.url.toString()) != APP_ORIGIN) {
                    Log.w(App.TAG, "${request.url}: ${error.description}")
                    serverLost()
                }
            }

            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                Log.w(App.TAG, "page crashed, starting over")
                recreate()
                return true
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                Log.d(App.TAG, "page: ${m.message()} (${m.sourceId()}:${m.lineNumber()})")
                return true
            }

            // the web player's full-screen button
            override fun onShowCustomView(view: View, callback: CustomViewCallback) {
                fullscreen?.let { onHideCustomView() }
                fullscreen = view
                fullscreenDone = callback
                root.addView(view, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
                root.requestApplyInsets()
                requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
                bars(false)
            }

            override fun onHideCustomView() {
                fullscreen?.let { root.removeView(it) }
                fullscreen = null
                fullscreenDone?.onCustomViewHidden()
                fullscreenDone = null
                requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
                bars(true)
                root.requestApplyInsets()
            }
        }

        music = Music(this) { bridge.event("music", music.state()) }
        bridge = Bridge(this, web, music)
        bridge.register()
        app.listeners += pageEvents

        getSystemService(ConnectivityManager::class.java).registerDefaultNetworkCallback(network)
        start(intent)
    }

    private val pageEvents: (String, Any?) -> Unit = { name, data -> bridge.event(name, data) }

    /** Online again (or another network): look for the server when the Downloads page shows. */
    private val network = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(n: Network) {
            main.postDelayed({ if (current == null) bridge.event("network") }, 1500)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.getStringExtra(OPEN) == "downloads") showApp("downloads")
    }

    private fun start(intent: Intent) {
        if (intent.getStringExtra(OPEN) == "downloads") return showApp("downloads")
        if (app.servers.shown().isEmpty()) return showApp("servers")
        showApp("start")  // "Looking for <server>…" while the app tries its addresses
        app.io.execute {
            val found = app.servers.findAny()
            app.onMain {
                if (found != null) loadServer(found.first, found.second)
                else { lost = app.servers.get(app.servers.last ?: "")?.name ?: app.servers.shown().first().name; showApp("downloads") }
            }
        }
    }

    /** Show server [s]'s web UI from [base]. */
    fun loadServer(s: Servers.Server, base: String) {
        current = s
        currentBase = Servers.origin(base)
        lost = null
        app.servers.opened(s.id, base)
        shareCookies(s, currentBase!!)
        clearHistory = true
        web.loadUrl("$currentBase/")
        downloadsQueued()
        // what was watched offline goes to the servers that answer
        app.io.execute {
            for (srv in app.servers.all()) {
                val at = if (srv.id == s.id) currentBase else app.servers.reach(srv.id) ?: continue
                app.progress.sync(srv.id, at!!, srv.token)
            }
        }
    }

    /** The app's own pages (assets/app): "downloads", "servers", "start". */
    fun showApp(page: String) {
        current = null
        currentBase = null
        clearHistory = true
        web.loadUrl("$APP_ORIGIN/app/index.html#/$page")
    }

    private fun serverLost() {
        lost = current?.name
        current?.let { app.servers.forget(it.id) }
        showApp("downloads")
    }

    /** A server's sign-in is a cookie per address: signed in at home, it's signed in away too. */
    private fun shareCookies(s: Servers.Server, base: String) {
        val cm = CookieManager.getInstance()
        if (!cm.getCookie(base).isNullOrBlank()) return
        val have = s.addresses.firstNotNullOfOrNull { a -> cm.getCookie(a)?.takeIf { it.isNotBlank() } } ?: return
        for (c in have.split(";")) cm.setCookie(base, c.trim() + "; Path=/; HttpOnly")
        cm.flush()
    }

    /** Downloads were queued or settings changed: start fetching (needs the app on screen) and ask once for the
     *  notification permission (Android 13+), so their progress shows. */
    fun downloadsQueued() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            && app.store.pending() > 0) {
            val prefs = getSharedPreferences("settings", MODE_PRIVATE)
            if (!prefs.getBoolean("asked_notifications", false)) {
                prefs.edit().putBoolean("asked_notifications", true).apply()
                requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
            }
        }
        DownloadService.start(this)
    }

    private fun bars(show: Boolean) {
        if (Build.VERSION.SDK_INT >= 30) {
            window.insetsController?.let {
                if (show) it.show(WindowInsets.Type.systemBars())
                else {
                    it.hide(WindowInsets.Type.systemBars())
                    it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                }
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = if (show) 0 else (View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY)
        }
    }

    @Deprecated("Back: out of full screen, then the page's history, then out of the app")
    override fun onBackPressed() {
        when {
            fullscreen != null -> web.webChromeClient?.onHideCustomView()
            web.canGoBack() -> web.goBack()
            else -> @Suppress("DEPRECATION") super.onBackPressed()
        }
    }

    override fun onStart() {
        super.onStart()
        web.onResume()
        if (current != null) DownloadService.start(this)
        else bridge.event("network")  // the Downloads page looks for the server again
    }

    // Home or another app: the web player's video pauses; music in the page plays on
    override fun onStop() {
        web.evaluateJavascript("document.querySelectorAll('video').forEach(function(v){v.pause()})", null)
        super.onStop()
    }

    override fun onDestroy() {
        app.listeners -= pageEvents
        try { getSystemService(ConnectivityManager::class.java).unregisterNetworkCallback(network) } catch (e: Exception) {}
        music.release()
        web.destroy()
        super.onDestroy()
    }

    private fun asset(path: String): WebResourceResponse? =
        try {
            val type = URLConnection.guessContentTypeFromName(path) ?: when {
                path.endsWith(".js") -> "text/javascript"
                path.endsWith(".css") -> "text/css"
                path.endsWith(".woff2") -> "font/woff2"
                path.endsWith(".svg") -> "image/svg+xml"
                else -> "application/octet-stream"
            }
            WebResourceResponse(type, null, assets.open(path))
        } catch (e: Exception) {
            null
        }

    private fun picture(path: String): WebResourceResponse? {
        val parts = path.split("/", limit = 3)  // <sid>/images/<rest>
        if (parts.size < 3 || parts[1] != "images" || parts[2].split("/").any { it == ".." }) return null
        val f = app.store.image(parts[0], "/api/images/" + Uri.decode(parts[2]))
        if (!f.isFile) return null
        val type = URLConnection.guessContentTypeFromName(f.name) ?: "image/jpeg"
        return WebResourceResponse(type, null, FileInputStream(f))
    }

    companion object {
        const val APP_ORIGIN = "https://appassets.androidplatform.net"
        const val OPEN = "open"
    }
}

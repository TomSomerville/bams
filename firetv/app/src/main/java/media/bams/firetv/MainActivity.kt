package media.bams.firetv

import android.annotation.SuppressLint
import android.app.Activity
import android.content.pm.ApplicationInfo
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.KeyEvent
import android.view.ViewGroup
import android.os.SystemClock
import android.view.InputDevice
import android.view.MotionEvent
import android.webkit.ConsoleMessage
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import org.json.JSONObject
import kotlin.math.roundToInt

/**
 * BAMS on a Fire TV: the TV app's page (tv/, bundled as assets/www) in a full-screen WebView, over ExoPlayer's video.
 * While a video plays the page is see-through (`html.playing`), so the video shows under the player's controls;
 * the rest of the time the page covers it. Keys the WebView doesn't give the page (Back, OK, media keys) are passed
 * on with the Samsung key codes the app already uses.
 */
@OptIn(UnstableApi::class)
class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var video: Video

    /** Android key -> the TV app's key code (tv/src/tizen.ts KEY) */
    private val keys = mapOf(
        KeyEvent.KEYCODE_BACK to 10009,
        KeyEvent.KEYCODE_BUTTON_B to 10009,
        // OK goes through the page's own handler (it opens the keyboard on a text box): see firetv.ts pressKey
        KeyEvent.KEYCODE_DPAD_CENTER to 13,
        KeyEvent.KEYCODE_BUTTON_A to 13,
        KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE to 10252,
        KeyEvent.KEYCODE_MEDIA_PLAY to 415,
        KeyEvent.KEYCODE_MEDIA_PAUSE to 19,
        KeyEvent.KEYCODE_MEDIA_STOP to 413,
        KeyEvent.KEYCODE_MEDIA_FAST_FORWARD to 417,
        KeyEvent.KEYCODE_MEDIA_REWIND to 412,
        KeyEvent.KEYCODE_MEDIA_NEXT to 10233,
        KeyEvent.KEYCODE_MEDIA_PREVIOUS to 10232,
    )

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val debuggable = applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
        WebView.setWebContentsDebuggingEnabled(debuggable)  // chrome://inspect from the PC, debug builds only

        val playerView = PlayerView(this).apply {
            useController = false
            resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
            setShutterBackgroundColor(Color.BLACK)
            isFocusable = false
            descendantFocusability = ViewGroup.FOCUS_BLOCK_DESCENDANTS
        }
        web = WebView(this).apply {
            setBackgroundColor(Color.TRANSPARENT)
            isFocusable = true
            isFocusableInTouchMode = true
        }
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        root.addView(playerView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        root.addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(root)

        val version = try { packageManager.getPackageInfo(packageName, 0).versionName } catch (e: Exception) { null } ?: "?"
        with(web.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true                       // localStorage: the server list, tokens, playback choices
            mediaPlaybackRequiresUserGesture = false       // music plays in the page's <audio>
            // the page is file:///android_asset/www (like Tizen's file://): its fonts and images are files too
            allowFileAccess = true
            @Suppress("DEPRECATION")
            allowFileAccessFromFileURLs = true
            useWideViewPort = true                         // the page is laid out at 1920 px wide (meta viewport)
            loadWithOverviewMode = true
            setSupportZoom(false)
            builtInZoomControls = false
            textZoom = 100
            userAgentString = "$userAgentString BAMS-FireTV/$version"
        }
        // 1920 CSS px across the screen, whatever its pixel density (setInitialScale counts device pixels)
        web.setInitialScale((resources.displayMetrics.widthPixels * 100f / 1920f).roundToInt())

        web.webViewClient = object : WebViewClient() {
            // only the app's own page: nothing navigates away from it
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                !request.url.toString().startsWith(PAGE_DIR)

            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                val why = if (Build.VERSION.SDK_INT >= 26 && !detail.didCrash()) "out of memory" else "crashed"
                Log.w(TAG, "page $why, starting over")
                recreate()
                return true
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                Log.d(TAG, "page: ${m.message()} (${m.sourceId()}:${m.lineNumber()})")
                return true
            }
        }

        video = Video(this, playerView, "BAMS-FireTV/$version") { event -> toPage("{type:\"player\",event:$event}") }
        web.addJavascriptInterface(Bridge(this, video), "BamsAndroid")
        web.loadUrl("${PAGE_DIR}index.html")
        web.requestFocus()
    }

    /** Hand the page an event (firetv.ts `bamsHost`). */
    private fun toPage(json: String) {
        web.evaluateJavascript("window.bamsHost&&window.bamsHost($json)", null)
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        val code = keys[event.keyCode] ?: return super.dispatchKeyEvent(event)
        if (event.action == KeyEvent.ACTION_DOWN) toPage(JSONObject().put("type", "key").put("code", code).toString())
        return true  // the key-up too: the page only listens for key-downs
    }

    /** Tap the page at ([x], [y]), fractions of its size. The WebView opens the keyboard on a text box only for a
     *  touch: InputMethodManager.showSoftInput brought Fire TV's keyboard up on a dead connection, it closed again at
     *  once and the box lost the focus. */
    fun tap(x: Float, y: Float) {
        val px = x.coerceIn(0f, 1f) * web.width
        val py = y.coerceIn(0f, 1f) * web.height
        val down = SystemClock.uptimeMillis()
        for ((action, at) in listOf(MotionEvent.ACTION_DOWN to down, MotionEvent.ACTION_UP to down + 50)) {
            val e = MotionEvent.obtain(down, at, action, px, py, 0)
            e.source = InputDevice.SOURCE_TOUCHSCREEN
            web.dispatchTouchEvent(e)
            e.recycle()
        }
    }

    // Home or another app in front: pause the video and the page; a pop-up over the app (Alexa) doesn't stop it
    override fun onStop() {
        video.pause()
        web.onPause()
        super.onStop()
    }

    override fun onStart() {
        super.onStart()
        web.onResume()
    }

    override fun onDestroy() {
        video.stop()
        web.destroy()
        super.onDestroy()
    }

    private companion object {
        const val TAG = "BAMS"
        const val PAGE_DIR = "file:///android_asset/www/"
    }
}

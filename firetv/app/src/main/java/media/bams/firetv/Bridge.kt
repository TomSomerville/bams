package media.bams.firetv

import android.content.Context
import android.net.ConnectivityManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.webkit.JavascriptInterface
import org.json.JSONObject
import java.net.Inet4Address
import java.util.concurrent.FutureTask
import java.util.concurrent.TimeUnit

/**
 * `window.BamsAndroid` in the page (firetv.ts). WebView calls these on its own thread; anything touching the player
 * or the views is handed to the main thread.
 */
class Bridge(private val activity: MainActivity, private val video: Video) {
    private val main = Handler(Looper.getMainLooper())

    // the decoders don't change while the app runs, and reading them takes a moment: once, when first asked
    private val info: String by lazy {
        JSONObject()
            .put("model", Build.MODEL)
            .put("name", deviceName())
            .put("version", appVersion())
            .put("ip", localIp() ?: JSONObject.NULL)
            .put("caps", Caps.json(activity))
            .toString()
    }

    @JavascriptInterface
    fun info(): String = info

    @JavascriptInterface
    fun exit() {
        main.post { activity.finish() }
    }

    /** OK on a text box: tap it at ([x], [y]), fractions of the page's width and height. */
    @JavascriptInterface
    fun showKeyboard(x: Double, y: Double) {
        main.post { activity.tap(x.toFloat(), y.toFloat()) }
    }

    @JavascriptInterface
    fun load(url: String, startMs: Double, hls: Boolean, id: Int) {
        main.post { video.load(url, startMs.toLong(), hls, id) }
    }

    @JavascriptInterface
    fun play() {
        main.post { video.play() }
    }

    @JavascriptInterface
    fun pause() {
        main.post { video.pause() }
    }

    @JavascriptInterface
    fun seek(ms: Double) {
        main.post { video.seek(ms.toLong()) }
    }

    @JavascriptInterface
    fun stop() {
        main.post { video.stop() }
    }

    /** Answers right away (the page waits for it), so this one waits for the main thread. */
    @JavascriptInterface
    fun selectAudio(n: Int): Boolean {
        val task = FutureTask { video.selectAudio(n) }
        main.post(task)
        return try {
            task.get(2, TimeUnit.SECONDS)
        } catch (e: Exception) {
            false
        }
    }

    /** The name the owner gave this Fire TV ("Tom's Fire TV Stick 4K"), shown in BAMS under Your TVs. */
    private fun deviceName(): String {
        val named = try {
            Settings.Global.getString(activity.contentResolver, "device_name")
        } catch (e: Exception) {
            null
        }
        return named?.takeIf { it.isNotBlank() } ?: "Fire TV ${Build.MODEL}"
    }

    private fun appVersion(): String =
        try {
            activity.packageManager.getPackageInfo(activity.packageName, 0).versionName ?: "?"
        } catch (e: Exception) {
            "?"
        }

    /** This device's IPv4 address on the home network, to look for BAMS servers next to it. */
    private fun localIp(): String? {
        val cm = activity.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val props = cm.getLinkProperties(cm.activeNetwork) ?: return null
        return props.linkAddresses.map { it.address }.firstOrNull { it is Inet4Address && !it.isLoopbackAddress }?.hostAddress
    }
}

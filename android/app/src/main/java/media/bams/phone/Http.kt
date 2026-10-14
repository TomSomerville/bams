package media.bams.phone

import android.webkit.CookieManager
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** A server's refusal or an unreachable server, with a message for the person. */
class HttpError(val status: Int, message: String) : IOException(message)

/**
 * Talking to a BAMS server. Signed in as the page is: for the server the app shows, the WebView's session cookie
 * (CookieManager, the same sign-in as the page's); for another server the web UI is connected to, its bearer token.
 */
object Http {
    const val TIMEOUT = 15_000

    fun open(url: String, token: String?, method: String = "GET", timeout: Int = TIMEOUT): HttpURLConnection {
        val c = URL(url).openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = timeout
        c.readTimeout = timeout * 2
        c.instanceFollowRedirects = true
        c.setRequestProperty("User-Agent", "BAMS-Android/${App.instance.version()}")
        if (token != null) c.setRequestProperty("Authorization", "Bearer $token")
        else CookieManager.getInstance().getCookie(url)?.let { c.setRequestProperty("Cookie", it) }
        return c
    }

    /** GET/PUT JSON; throws HttpError with the server's `detail` on a refusal. */
    fun json(url: String, token: String?, method: String = "GET", body: JSONObject? = null, timeout: Int = TIMEOUT): JSONObject {
        val c = open(url, token, method, timeout)
        try {
            if (body != null) {
                c.doOutput = true
                c.setRequestProperty("Content-Type", "application/json")
                c.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            val code = try { c.responseCode } catch (e: IOException) { throw HttpError(0, "Can't reach the server.") }
            val text = (if (code < 400) c.inputStream else c.errorStream)?.use { it.readBytes().decodeToString() } ?: ""
            if (code >= 400) throw HttpError(code, detail(code, text))
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        } finally {
            c.disconnect()
        }
    }

    fun detail(code: Int, text: String): String {
        val d = try { JSONObject(text).opt("detail") } catch (e: Exception) { null }
        return when {
            d is String -> d
            code == 401 -> "You're signed out of this server: open it and sign in again."
            else -> "The server answered $code."
        }
    }

    /** `/api/hello` at [base]: {app, version, name, id} if a BAMS server answers there quickly, else null. */
    fun hello(base: String, timeout: Int = 3000): JSONObject? =
        try {
            val h = json("$base/api/hello", null, timeout = timeout)
            if (h.optString("app") == "bams") h else null
        } catch (e: Exception) {
            null
        }
}

package media.bams.phone

import android.annotation.SuppressLint
import android.net.Uri
import android.util.Log
import android.webkit.WebView
import androidx.webkit.JavaScriptReplyProxy
import androidx.webkit.WebMessageCompat
import androidx.webkit.WebViewCompat
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * The page's way to the app (web/src/android.ts): `window.bamsAndroid`, a WebMessageListener that only the app's
 * own pages and the app's servers' pages get (origin rules). A message is {id, type, ...}; the answer is
 * {reply: id, ok, data | error}; events go to the page as {event, data}.
 *
 * A server's page may ask for downloads and their state; only the app's own pages (Downloads, Servers) may play
 * files, change servers or read the whole catalog.
 */
@SuppressLint("RequiresFeature")
class Bridge(private val activity: MainActivity, private val web: WebView, private val music: Music) {
    private val app = activity.application as App
    private var proxy: JavaScriptReplyProxy? = null
    private var registered = false
    /** page address -> server id, for servers met through the web UI (asked once) */
    private val ids = mutableMapOf<String, String>()

    fun register() {
        if (registered) WebViewCompat.removeWebMessageListener(web, NAME)
        val rules = app.servers.origins() + MainActivity.APP_ORIGIN
        WebViewCompat.addWebMessageListener(web, NAME, rules) { _, message, origin, isMainFrame, reply ->
            if (isMainFrame) handle(message, origin, reply)
        }
        registered = true
    }

    /** An event for the page (it fires `bams:<name>` on window). */
    fun event(name: String, data: Any? = null) {
        try {
            proxy?.postMessage(JSONObject().put("event", name).put("data", data ?: JSONObject.NULL).toString())
        } catch (e: Exception) { /* page gone */ }
    }

    private fun handle(message: WebMessageCompat, origin: Uri, reply: JavaScriptReplyProxy) {
        val m = try { JSONObject(message.data ?: return) } catch (e: Exception) { return }
        proxy = reply
        val id = m.optInt("id")
        val ownPage = origin.toString().trimEnd('/') == MainActivity.APP_ORIGIN
        val done = { data: Any? ->
            try { reply.postMessage(JSONObject().put("reply", id).put("ok", true).put("data", data ?: JSONObject.NULL).toString()) } catch (e: Exception) {}
        }
        val fail = { why: String ->
            try { reply.postMessage(JSONObject().put("reply", id).put("ok", false).put("error", why).toString()) } catch (e: Exception) {}
        }
        // work that waits on the network or the disk: off the main thread, answered on it
        val later = { work: () -> Any? ->
            app.io.execute {
                try {
                    val r = work()
                    app.onMain { done(r) }
                } catch (e: Exception) {
                    Log.w(App.TAG, "${m.optString("type")}: ${e.message}")
                    app.onMain { fail(e.message ?: "Something went wrong.") }
                }
            }
        }
        val pageOrigin = Servers.origin(origin.toString())
        when (m.optString("type")) {
            "hello" -> done(null)
            "info" -> done(info())
            "download" -> later {
                val (sid, token, base) = server(m.getJSONObject("server"), pageOrigin)
                val manifest = Http.json(base + m.getString("path"), token)
                app.store.add(sid, m.getString("key"), m.getString("title"), manifest)
                app.onMain { activity.downloadsQueued() }
                app.emit("downloads")
                null
            }
            "status" -> later {
                val (sid) = server(m.getJSONObject("server"), pageOrigin)
                val keys = m.getJSONArray("keys")
                JSONObject().apply { for (i in 0 until keys.length()) put(keys.getString(i), app.store.status(sid, keys.getString(i))) }
            }
            "remove" -> later {
                val (sid) = server(m.getJSONObject("server"), pageOrigin)
                app.store.remove("$sid|${m.getString("key")}")
                app.emit("downloads")
                null
            }
            "setLocation" -> { app.store.location = m.getString("volume"); done(info()) }
            "setWifiOnly" -> { app.store.wifiOnly = m.getBoolean("on"); activity.downloadsQueued(); done(info()) }
            "openDownloads" -> { activity.showApp("downloads"); done(null) }
            "openServers" -> { activity.showApp("servers"); done(null) }
            // the app's music player, for music streamed from the page's server(s) too (lock screen, screen off)
            "musicStream" -> {
                val items = m.getJSONArray("items")
                val bad = (0 until items.length()).any { i ->
                    val t = items.getJSONObject(i)
                    listOfNotNull(t.str("url"), t.str("fallback"), t.str("art")).any { !it.startsWith("http://") && !it.startsWith("https://") }
                }
                if (bad) fail("Only server addresses can be streamed.")
                else { music.stream(items, m.optInt("index")); done(null) }
            }
            "musicCmd" -> {
                music.command(m.getString("cmd"), if (m.has("value")) m.optDouble("value") else null, if (m.has("to")) m.optInt("to") else null)
                done(null)
            }
            "musicState" -> done(music.state())
            else -> if (ownPage) appPage(m, done, fail, later) else fail("Not allowed here.")
        }
    }

    /** What only the app's own pages may do. */
    private fun appPage(m: JSONObject, done: (Any?) -> Unit, fail: (String) -> Unit, later: (() -> Any?) -> Unit) {
        when (m.optString("type")) {
            "library" -> done(app.store.library(app.servers).put("progress", app.progress.json()))
            "removeDownload" -> later { app.store.remove(m.getString("key")); app.emit("downloads"); null }
            "servers" -> later { servers(m.optBoolean("check")) }
            "current" -> done(activity.lost?.let { JSONObject().put("lost", it) })
            "addServer" -> later {
                val (s, base) = app.servers.add(m.getString("address"))
                app.onMain { register(); activity.loadServer(s, base) }
                JSONObject().put("id", s.id).put("name", s.name)
            }
            "removeServer" -> { app.servers.remove(m.getString("id")); register(); done(null) }
            "removeAddress" -> { app.servers.removeAddress(m.getString("id"), m.getString("address")); register(); done(null) }
            "openServer" -> later {
                val s = app.servers.get(m.getString("id")) ?: throw HttpError(0, "That server isn't in the list any more.")
                val base = app.servers.reach(s.id, fresh = true)
                    ?: throw HttpError(0, "Can't reach ${s.name} right now. Your downloads still play.")
                app.onMain { activity.loadServer(s, base) }
                null
            }
            "playVideo" -> {
                val q = m.getJSONArray("queue")
                val out = JSONArray()
                var index = m.optInt("index")
                for (i in 0 until q.length()) {
                    val v = q.getJSONObject(i)
                    val sid = v.getString("sid")
                    val f = app.store.fileFor(sid, v.getInt("id"))
                    if (f == null) { if (i < m.optInt("index")) index--; continue }
                    val dir = app.store.dir(f)!!
                    val subs = JSONArray()
                    for (k in 0 until f.subs.length()) {
                        val s = f.subs.getJSONObject(k)
                        subs.put(JSONObject(s.toString()).put("path", File(File(dir, "subs"), Store.safeName(s.getString("id")) + ".vtt").path))
                    }
                    out.put(JSONObject(v.toString()).put("path", File(dir, f.name).path).put("subs", subs))
                }
                if (out.length() == 0) fail("That file isn't on this phone (still downloading, or its SD card is out).")
                else {
                    music.pause()
                    PlayerActivity.start(activity, out, index.coerceIn(0, out.length() - 1))
                    done(null)
                }
            }
            "musicPlay" -> {
                val ts = m.getJSONArray("tracks")
                val out = JSONArray()
                var index = m.optInt("index")
                for (i in 0 until ts.length()) {
                    val t = ts.getJSONObject(i)
                    val sid = t.getString("sid")
                    val f = app.store.file("$sid|${t.getInt("file")}")?.takeIf { it.state == "done" }
                    val path = f?.let { app.store.target(it) }
                    if (path == null || !path.exists()) { if (i < m.optInt("index")) index--; continue }
                    val art = t.str("poster")?.let { app.store.image(sid, it).path }
                    out.put(JSONObject(t.toString()).put("path", path.path).put("art", art))
                }
                if (out.length() == 0) fail("Those tracks aren't on this phone yet.")
                else { music.play(out, index.coerceIn(0, out.length() - 1), m.optBoolean("shuffle")); done(null) }
            }
            else -> fail("The app doesn't know \"${m.optString("type")}\".")
        }
    }

    private fun info(): JSONObject {
        val vols = Volumes.all(activity)
        val loc = app.store.location.takeIf { l -> vols.any { it.id == l } } ?: vols.firstOrNull()?.id ?: "primary"
        return JSONObject().put("version", app.version()).put("location", loc)
            .put("volumes", JSONArray(vols.map { it.json() })).put("wifiOnly", app.store.wifiOnly)
            .put("used", app.store.used()).put("codecs", Caps.json())
    }

    /** The app's servers with the address each answers at now (null: out of reach). */
    private fun servers(check: Boolean): JSONObject {
        val list = JSONArray()
        for (s in app.servers.shown()) {
            list.put(JSONObject().put("id", s.id).put("name", s.name).put("addresses", JSONArray(s.addresses))
                .put("online", app.servers.reach(s.id, fresh = check) ?: JSONObject.NULL))
        }
        return JSONObject().put("servers", list).put("last", app.servers.last)
    }

    /** Which server a page means, how to sign in there, and where it is: this page's own server (the WebView's
     *  cookie), or another one the web UI is connected to (its token). */
    private fun server(o: JSONObject, pageOrigin: String): Triple<String, String?, String> {
        val token = o.str("token")
        if (token == null) {
            val s = app.servers.forOrigin(pageOrigin) ?: throw HttpError(0, "This page isn't one of the app's servers.")
            return Triple(s.id, null, pageOrigin)
        }
        val base = Servers.origin(o.getString("url"))
        val sid = synchronized(ids) { ids[base] } ?: run {
            val h = Http.hello(base, 5000) ?: throw HttpError(0, "Can't reach ${o.optString("name", base)} right now.")
            h.getString("id").also { synchronized(ids) { ids[base] = it } }
        }
        app.servers.remember(sid, o.optString("name"), base, token)
        return Triple(sid, token, base)
    }

    companion object {
        const val NAME = "bamsAndroid"
    }
}

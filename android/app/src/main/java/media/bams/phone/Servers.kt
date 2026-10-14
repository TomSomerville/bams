package media.bams.phone

import android.content.Context
import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * The BAMS servers this phone knows, each with every address it was reached at (home: 192.168.1.5:8484, away: a
 * domain). A server is known by the id `/api/hello` gives (the same at every address), so its downloads stay its own
 * whichever address it's reached at. `shown` ones are the app's servers (the web UI is loaded from them); the others
 * only came in through the web UI's "other servers" (their token is kept for downloads and progress).
 */
class Servers(context: Context) {
    data class Server(
        val id: String,
        var name: String,
        val addresses: MutableList<String>,
        var shown: Boolean,
        /** bearer token for a server the web UI connected to (not shown by the app); null = the WebView's cookie */
        var token: String? = null,
    ) {
        fun json(): JSONObject = JSONObject().put("id", id).put("name", name).put("addresses", JSONArray(addresses))
            .put("shown", shown).put("token", token)
    }

    private val file = File(context.filesDir, "servers.json")
    private val list = mutableListOf<Server>()
    /** id of the server last opened (tried first) */
    var last: String? = null
        private set
    /** id -> (address that answered, when) */
    private val reached = mutableMapOf<String, Pair<String?, Long>>()

    init {
        try {
            val o = JSONObject(file.readText())
            last = o.str("last")
            val a = o.getJSONArray("servers")
            for (i in 0 until a.length()) {
                val s = a.getJSONObject(i)
                val addrs = s.getJSONArray("addresses")
                list += Server(s.getString("id"), s.getString("name"),
                    MutableList(addrs.length()) { addrs.getString(it) }, s.optBoolean("shown", true), s.str("token"))
            }
        } catch (e: Exception) { /* none yet */ }
    }

    @Synchronized
    private fun save() {
        val o = JSONObject().put("last", last).put("servers", JSONArray(list.map { it.json() }))
        file.writeText(o.toString())
    }

    @Synchronized fun all(): List<Server> = list.toList()
    @Synchronized fun shown(): List<Server> = list.filter { it.shown }
    @Synchronized fun get(id: String): Server? = list.find { it.id == id }

    /** Which server an address/page origin belongs to. */
    @Synchronized
    fun forOrigin(origin: String): Server? = list.find { s -> s.addresses.any { origin(it) == origin(origin) } }

    /** Every address of the app's servers, as WebView origin rules (where the page may use the bridge). */
    @Synchronized
    fun origins(): Set<String> = list.filter { it.shown }.flatMap { it.addresses }.map(::origin).toSet()

    /** Connect to what someone typed ("192.168.1.5", "media.example.com", "host:9000", "https://…"): the server
     *  that answers is added (or this address is added to it, when it's one already known). */
    fun add(typed: String): Pair<Server, String> {
        val tried = candidates(typed)
        for (base in tried) {
            val h = Http.hello(base, 5000) ?: continue
            val s = remember(h.getString("id"), h.optString("name", base), base, null, shown = true)
            synchronized(this) { last = s.id; reached[s.id] = base to System.currentTimeMillis(); save() }
            return s to base
        }
        throw HttpError(0, "No BAMS server answered at ${tried.first()}. Check the address, and that this phone is on " +
            "a network that reaches it.")
    }

    /** A server met through the page (its address, maybe a token): kept, merged with what's known. */
    @Synchronized
    fun remember(id: String, name: String, address: String, token: String?, shown: Boolean = false): Server {
        val base = origin(address)
        val s = list.find { it.id == id } ?: Server(id, name, mutableListOf(), shown).also { list += it }
        if (name.isNotBlank()) s.name = name
        if (base !in s.addresses) s.addresses += base
        if (shown) s.shown = true
        if (token != null) s.token = token
        save()
        return s
    }

    @Synchronized
    fun remove(id: String) {
        list.removeAll { it.id == id }
        if (last == id) last = null
        save()
    }

    @Synchronized
    fun removeAddress(id: String, address: String) {
        get(id)?.addresses?.remove(address)
        save()
    }

    @Synchronized
    fun opened(id: String, address: String) {
        last = id
        reached[id] = origin(address) to System.currentTimeMillis()
        get(id)?.let { s -> s.addresses.remove(origin(address)); s.addresses.add(0, origin(address)) }  // tried first next time
        save()
    }

    /** An address of server [id] that answers now (the last one that did first), or null. Blocking: not on the main thread. */
    fun reach(id: String, fresh: Boolean = false): String? {
        val s = get(id) ?: return null
        synchronized(this) {
            val r = reached[id]
            if (!fresh && r != null && System.currentTimeMillis() - r.second < 20_000) return r.first
        }
        val known = synchronized(this) { reached[id]?.first }
        val order = listOfNotNull(known) + s.addresses.filter { it != known }
        val hit = order.firstOrNull { Http.hello(it)?.optString("id") == id }
        synchronized(this) { reached[id] = hit to System.currentTimeMillis() }
        return hit
    }

    /** The first of the app's servers that answers (the last opened first), with its address. */
    fun findAny(): Pair<Server, String>? {
        val order = shown().sortedBy { if (it.id == last) 0 else 1 }
        for (s in order) reach(s.id, fresh = true)?.let { return s to it }
        return null
    }

    @Synchronized
    fun forget(id: String) {
        reached.remove(id)
    }

    companion object {
        const val DEFAULT_PORT = 8484

        fun origin(url: String): String {
            val u = Uri.parse(url.trim())
            val port = if (u.port > 0) ":${u.port}" else ""
            return "${u.scheme}://${u.host}$port".lowercase()
        }

        /** Addresses to try for what someone typed, like the web UI's servers.tsx. */
        fun candidates(typed: String): List<String> {
            val a = typed.trim().trimEnd('/').removeSuffix("/api")
            if (a.isEmpty()) throw HttpError(0, "Type the address of your BAMS server.")
            if (Regex("^https?://", RegexOption.IGNORE_CASE).containsMatchIn(a)) return listOf(origin(a))
            if (Regex("[\\s/\\\\?#@]").containsMatchIn(a)) throw HttpError(0, "That doesn't look like a server address.")
            if (Regex(":\\d+$").containsMatchIn(a)) return listOf("http://$a", "https://$a")
            return listOf("http://$a:$DEFAULT_PORT", "https://$a", "http://$a")
        }
    }
}

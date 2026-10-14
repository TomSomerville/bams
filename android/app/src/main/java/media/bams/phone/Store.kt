package media.bams.phone

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * The downloads catalog. A *root* is what someone asked for (a movie, an episode, a season, a show, a track, an
 * album, an artist, a playlist), keyed "<server id>|item:5" / "|playlist:3", with the server's manifest for it
 * (`GET /api/items/{id}/download`: the items as the API shows them, music's queue, the files, the pictures). A
 * *file* is one original file, kept once however many roots want it (an episode of a downloaded season that was
 * also downloaded alone, a CUE album's tracks): it's deleted when the last root that wants it is removed.
 *
 * Files go to the volume picked in settings at the time (Volumes); the catalog, the manifests and the pictures
 * stay in the app's internal storage, so the library still shows when an SD card is out.
 */
class Store(private val context: Context) {
    class FileEntry(
        val sid: String, val fid: Int, val name: String, val size: Long, val url: String, val volume: String,
        var got: Long, var state: String, var error: String?,
        val items: MutableSet<Int>, val roots: MutableSet<String>, val subs: JSONArray, val audio: JSONArray,
    ) {
        val key get() = "$sid|$fid"

        fun json(): JSONObject = JSONObject().put("sid", sid).put("fid", fid).put("name", name).put("size", size)
            .put("url", url).put("volume", volume).put("got", got).put("state", state).put("error", error)
            .put("items", JSONArray(items.toList())).put("roots", JSONArray(roots.toList())).put("subs", subs)
            .put("audio", audio)

        companion object {
            fun from(o: JSONObject) = FileEntry(
                o.getString("sid"), o.getInt("fid"), o.getString("name"), o.getLong("size"), o.getString("url"),
                o.getString("volume"), o.getLong("got"), o.getString("state"), o.str("error"),
                ints(o.getJSONArray("items")).toMutableSet(), strings(o.getJSONArray("roots")).toMutableSet(),
                o.getJSONArray("subs"), o.optJSONArray("audio") ?: JSONArray(),
            )
        }
    }

    class Root(val key: String, val sid: String, val kind: String, val id: Int, val title: String, val added: Long,
               var error: String?) {
        fun json(): JSONObject = JSONObject().put("key", key).put("sid", sid).put("kind", kind).put("id", id)
            .put("title", title).put("added", added).put("error", error)

        companion object {
            fun from(o: JSONObject) = Root(o.getString("key"), o.getString("sid"), o.getString("kind"), o.getInt("id"),
                o.getString("title"), o.getLong("added"), o.str("error"))
        }
    }

    private val file = File(context.filesDir, "downloads.json")
    private val manifestDir = File(context.filesDir, "manifests")
    val imageDir = File(context.filesDir, "images")
    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)
    private val roots = linkedMapOf<String, Root>()
    private val files = linkedMapOf<String, FileEntry>()
    private val manifests = mutableMapOf<String, JSONObject>()

    /** why queued files aren't moving ("wifi": waiting for Wi-Fi), set by DownloadService */
    @Volatile var waiting: String? = null

    init {
        try {
            val o = JSONObject(file.readText())
            o.getJSONArray("roots").let { a -> for (i in 0 until a.length()) Root.from(a.getJSONObject(i)).let { roots[it.key] = it } }
            o.getJSONArray("files").let { a -> for (i in 0 until a.length()) FileEntry.from(a.getJSONObject(i)).let { files[it.key] = it } }
            // a download cut off when the app was closed carries on from where its file got to
            for (f in files.values) if (f.state == "downloading") f.state = "queued"
        } catch (e: Exception) { /* nothing downloaded yet */ }
    }

    @Synchronized
    fun save() {
        val o = JSONObject().put("roots", JSONArray(roots.values.map { it.json() }))
            .put("files", JSONArray(files.values.map { it.json() }))
        val tmp = File(file.path + ".tmp")
        tmp.writeText(o.toString())
        tmp.renameTo(file)
    }

    // ---- settings

    var location: String
        get() = prefs.getString("location", null) ?: "primary"
        set(v) = prefs.edit().putString("location", v).apply()

    var wifiOnly: Boolean
        get() = prefs.getBoolean("wifi_only", true)
        set(v) = prefs.edit().putBoolean("wifi_only", v).apply()

    // ---- adding and removing

    private fun manifestFile(key: String): File {
        val (sid, what) = key.split("|", limit = 2)
        return File(File(manifestDir, sid), what.replace(':', '-') + ".json")
    }

    fun manifest(key: String): JSONObject? = synchronized(this) {
        manifests[key] ?: try { JSONObject(manifestFile(key).readText()).also { manifests[key] = it } } catch (e: Exception) { null }
    }

    /** Queue what [m] (a manifest from server [sid]) lists, as root [what] ("item:5"). Files already here are kept. */
    @Synchronized
    fun add(sid: String, what: String, title: String, m: JSONObject): Root {
        val key = "$sid|$what"
        val (kind, id) = what.split(":", limit = 2)
        val root = roots[key] ?: Root(key, sid, kind, id.toInt(), title, System.currentTimeMillis(), null)
        root.error = null
        roots[key] = root
        manifestFile(key).apply { parentFile?.mkdirs() }.writeText(m.toString())
        manifests[key] = m
        val fs = m.getJSONArray("files")
        for (i in 0 until fs.length()) {
            val f = fs.getJSONObject(i)
            val fkey = "$sid|${f.getInt("id")}"
            val e = files[fkey] ?: FileEntry(sid, f.getInt("id"), safeName(f.getString("name")), f.optLong("size"),
                f.getString("url"), location, 0, "queued", null, mutableSetOf(), mutableSetOf(), f.optJSONArray("subtitles") ?: JSONArray(),
                f.optJSONArray("audio") ?: JSONArray()).also { files[fkey] = it }
            e.roots += key
            e.items += ints(f.getJSONArray("items"))
            if (e.state == "failed") { e.state = "queued"; e.error = null }  // asked again: try again
        }
        save()
        return root
    }

    /** Take root [key] off the phone: the files only it wanted are deleted (a running one is stopped first by
     *  DownloadService, which sees its state change). */
    @Synchronized
    fun remove(key: String) {
        roots.remove(key) ?: return
        manifests.remove(key)
        manifestFile(key).delete()
        for (f in files.values.toList()) {
            if (!f.roots.remove(key) || f.roots.isNotEmpty()) continue
            files.remove(f.key)
            f.state = "removed"
            deleteFiles(f)
        }
        pruneImages(key.substringBefore("|"))
        save()
    }

    fun deleteFiles(f: FileEntry) {
        dir(f)?.deleteRecursively()
    }

    /** Pictures no manifest of server [sid] mentions any more. */
    private fun pruneImages(sid: String) {
        val keep = mutableSetOf<String>()
        for (r in roots.values.filter { it.sid == sid }) {
            val a = manifest(r.key)?.optJSONArray("images") ?: continue
            for (i in 0 until a.length()) keep += a.getString(i).removePrefix("/api/images/")
        }
        val base = File(imageDir, sid)
        base.walkBottomUp().filter { it.isFile }.forEach { if (it.relativeTo(base).invariantSeparatorsPath !in keep) it.delete() }
    }

    // ---- where files are

    /** The folder of a file's download (its original and its subtitles), or null when its volume is gone. */
    fun dir(f: FileEntry): File? {
        if (!Volumes.mounted(context, f.volume)) return null
        val v = Volumes.get(context, f.volume) ?: return null
        return File(File(v.dir, f.sid), f.fid.toString())
    }

    fun target(f: FileEntry): File? = dir(f)?.let { File(it, f.name) }

    fun image(sid: String, url: String): File = File(File(imageDir, sid), url.removePrefix("/api/images/"))

    // ---- for DownloadService

    @Synchronized
    fun file(key: String): FileEntry? = files[key]

    /** The downloaded file of movie/episode [item] of server [sid], if it's here. */
    @Synchronized
    fun fileFor(sid: String, item: Int): FileEntry? =
        files.values.firstOrNull { it.sid == sid && item in it.items && it.state == "done" && dir(it) != null }

    @Synchronized
    fun rootsOf(f: FileEntry): List<Root> = f.roots.mapNotNull { roots[it] }

    @Synchronized
    fun pending(): Int = files.values.count { it.state == "queued" || it.state == "downloading" }

    @Synchronized
    fun allRoots(): List<Root> = roots.values.toList()

    // ---- what the pages see

    /** State of one root, or of an item that's part of other downloads (an episode of a downloaded season). */
    @Synchronized
    fun status(sid: String, what: String): JSONObject {
        val key = "$sid|$what"
        roots[key]?.let { return rootState(it) }
        val (kind, idText) = what.split(":", limit = 2)
        val id = idText.toIntOrNull() ?: return none()
        if (kind != "item") return none()
        // a movie/episode/track in some download: its own file(s)
        val own = files.values.filter { it.sid == sid && id in it.items }
        if (own.isNotEmpty()) return state(own, null).put("within", own.first().roots.firstOrNull()?.substringAfter("|"))
        // a season/album inside a downloaded show/artist
        for (r in roots.values.filter { it.sid == sid && it.kind == "item" }) {
            val items = manifest(r.key)?.optJSONArray("items") ?: continue
            for (i in 0 until items.length()) {
                val d = items.getJSONObject(i)
                if (d.optInt("id") != id) continue
                val anc = d.optJSONArray("ancestors") ?: continue
                val under = (0 until anc.length()).any { anc.getJSONObject(it).optInt("id") == r.id }
                if (under) return rootState(r).put("within", r.key.substringAfter("|"))
            }
        }
        return none()
    }

    private fun none() = JSONObject().put("state", "none").put("progress", 0).put("bytes", 0)

    private fun rootState(r: Root): JSONObject = state(files.values.filter { r.key in it.roots }, r.error)

    private fun state(fs: List<FileEntry>, error: String?): JSONObject {
        val total = fs.sumOf { it.size }
        val got = fs.sumOf { minOf(it.got, it.size) }
        val s = when {
            error != null && fs.isEmpty() -> "failed"
            fs.isEmpty() -> "failed"
            fs.all { it.state == "done" } -> "done"
            fs.any { it.state == "downloading" } -> "downloading"
            fs.any { it.state == "queued" } -> if (waiting != null) "paused" else "queued"
            else -> "failed"
        }
        val err = error ?: fs.firstOrNull { it.state == "failed" }?.error
            ?: if (fs.isEmpty()) "Nothing in it could be downloaded (files missing on the server)." else null
        return JSONObject().put("state", s).put("progress", if (total > 0) got.toDouble() / total else 0.0)
            .put("bytes", total).put("error", if (s == "failed") err else null)
    }

    /** Bytes the downloads take. */
    @Synchronized
    fun used(): Long = files.values.sumOf { minOf(it.got, it.size) }

    /** Everything the Downloads pages show: each download with its state and manifest, and which files are here. */
    @Synchronized
    fun library(servers: Servers): JSONObject {
        val rs = JSONArray()
        for (r in roots.values) {
            rs.put(r.json().put("status", rootState(r)).put("manifest", manifest(r.key)))
        }
        val fs = JSONObject()
        for (f in files.values) {
            val here = f.state == "done" && dir(f) != null
            fs.put(f.key, JSONObject().put("state", if (f.state == "done" && !here) "missing" else f.state)
                .put("size", f.size).put("got", f.got).put("audio", f.audio))
        }
        val ss = JSONArray()
        for (s in servers.all()) ss.put(JSONObject().put("id", s.id).put("name", s.name).put("shown", s.shown))
        return JSONObject().put("roots", rs).put("files", fs).put("servers", ss).put("used", used())
    }

    companion object {
        fun ints(a: JSONArray) = List(a.length()) { a.getInt(it) }
        fun strings(a: JSONArray) = List(a.length()) { a.getString(it) }

        /** A file name that's safe on any phone storage (FAT SD cards refuse some characters). */
        fun safeName(name: String): String =
            name.replace(Regex("[\\\\/:*?\"<>|\\x00-\\x1f]"), "_").trim().ifEmpty { "file" }.take(180)
    }
}

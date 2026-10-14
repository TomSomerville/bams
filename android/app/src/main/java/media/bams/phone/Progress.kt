package media.bams.phone

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.File

/**
 * Where you stopped in a downloaded movie/episode, kept on the phone and sent to its server the next time it's
 * reached (`PUT /api/items/{id}/progress`), so Continue Watching there is right after watching offline.
 */
class Progress(context: Context) {
    private val file = File(context.filesDir, "progress.json")
    /** server id -> item id -> {position, duration, at, sent} */
    private val data: JSONObject = try { JSONObject(file.readText()) } catch (e: Exception) { JSONObject() }

    @Synchronized
    fun record(sid: String, item: Int, position: Double, duration: Double?) {
        val s = data.optJSONObject(sid) ?: JSONObject().also { data.put(sid, it) }
        s.put(item.toString(), JSONObject().put("position", position).put("duration", duration)
            .put("at", System.currentTimeMillis()).put("sent", false))
        file.writeText(data.toString())
    }

    @Synchronized
    fun get(sid: String, item: Int): JSONObject? = data.optJSONObject(sid)?.optJSONObject(item.toString())

    @Synchronized
    fun json(): JSONObject = JSONObject(data.toString())

    @Synchronized
    private fun unsent(sid: String): List<Pair<Int, JSONObject>> {
        val s = data.optJSONObject(sid) ?: return emptyList()
        return s.keys().asSequence().map { it.toInt() to s.getJSONObject(it.toString()) }
            .filter { !it.second.optBoolean("sent") }.toList()
    }

    /** Send what was watched offline to server [sid] at [base]. Blocking. */
    fun sync(sid: String, base: String, token: String?) {
        for ((item, p) in unsent(sid)) {
            val body = JSONObject().put("position", p.getDouble("position"))
            if (!p.isNull("duration")) body.put("duration", p.getDouble("duration"))
            try {
                Http.json("$base/api/items/$item/progress", token, "PUT", body)
                synchronized(this) {
                    if (p.getLong("at") == get(sid, item)?.getLong("at")) p.put("sent", true)  // not overwritten since
                    file.writeText(data.toString())
                }
            } catch (e: HttpError) {
                if (e.status == 0) return  // gone again
                if (e.status == 404) synchronized(this) { p.put("sent", true) }  // removed from the server
                Log.w(App.TAG, "progress of $item not sent: ${e.message}")
            }
        }
    }
}

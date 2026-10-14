package media.bams.phone

import android.content.ComponentName
import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import androidx.media3.session.SessionCommand
import android.os.Bundle
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executor

/**
 * The pages' remote for MusicService, the app's one music player (it plays on with the screen off and shows on the
 * lock screen): downloaded tracks from the Downloads pages (`play`), and music streamed from a server from its own
 * web pages (`stream`, web/src/music.tsx AppMusicProvider; how converted tracks seek: Streams.kt). Pause, skip, seek,
 * reorder, take out.
 */
class Music(private val context: Context, private val changed: () -> Unit) {
    private var controller: MediaController? = null
    private val main = Handler(Looper.getMainLooper())
    private val onMain = Executor { main.post(it) }
    private val future = MediaController.Builder(context, SessionToken(context, ComponentName(context, MusicService::class.java)))
        .buildAsync()
    private val listener = object : Player.Listener {
        override fun onEvents(player: Player, events: Player.Events) = changed()
    }
    private val ticker = object : Runnable {
        override fun run() {
            if (controller?.isPlaying == true) changed()
            main.postDelayed(this, 1000)
        }
    }

    init {
        future.addListener({
            controller = try { future.get() } catch (e: Exception) { null }
            controller?.addListener(listener)
            changed()
        }, onMain)
        main.postDelayed(ticker, 1000)
    }

    private fun meta(t: JSONObject, art: Uri?): MediaMetadata {
        val m = MediaMetadata.Builder().setTitle(t.str("title")).setArtist(t.str("artist"))
            .setAlbumTitle(t.str("album")).setIsPlayable(true)
        if (art != null) m.setArtworkUri(art)
        return m.build()
    }

    private fun num(t: JSONObject, k: String): Double? = if (t.isNull(k)) null else t.getDouble(k)

    /** Downloaded tracks, [tracks]: each {sid, id, path, title, artist, album, art (a local file), start, end}; seconds. */
    fun play(tracks: JSONArray, index: Int, shuffle: Boolean) {
        val c = controller ?: return
        val items = (0 until tracks.length()).map { i ->
            val t = tracks.getJSONObject(i)
            val art = t.str("art")?.let { File(it) }?.takeIf { it.exists() }?.let { Uri.fromFile(it) }
            Streams.build("${t.getString("sid")}|${t.getInt("id")}", Uri.fromFile(File(t.getString("path"))), meta(t, art),
                num(t, "start"), num(t, "end"))
        }
        Streams.all.clear()
        c.shuffleModeEnabled = shuffle
        c.setMediaItems(items, index.coerceIn(0, maxOf(0, items.size - 1)), 0)
        c.prepare()
        c.play()
    }

    /** Music from a server's page: [items] each {key, url (a ticket URL: no headers needed), transcode, fallback,
     *  title, artist, album, art (URL), start, end, duration}, in play order (the page shuffles). */
    fun stream(items: JSONArray, index: Int) {
        val c = controller ?: return
        val list = (0 until items.length()).map { i ->
            val t = items.getJSONObject(i)
            Streams.Stream(t.getString("key"), t.getString("url"), t.optBoolean("transcode"), t.str("fallback"),
                num(t, "start") ?: 0.0, num(t, "end"), num(t, "duration"), 0.0, meta(t, t.str("art")?.let { Uri.parse(it) }))
        }
        synchronized(Streams.all) {
            Streams.all.clear()
            for (s in list) Streams.all[s.key] = s
        }
        c.shuffleModeEnabled = false
        c.setMediaItems(list.map { Streams.item(it) }, index.coerceIn(0, maxOf(0, list.size - 1)), 0)
        c.prepare()
        c.play()
    }

    fun command(cmd: String, value: Double?, to: Int? = null) {
        val c = controller ?: return
        when (cmd) {
            "toggle" -> if (c.isPlaying) c.pause() else c.play()
            "play" -> c.play()
            "pause" -> c.pause()
            "next" -> c.seekToNextMediaItem()
            "prev" -> if (c.currentPosition > 3000) seek(c, 0) else c.seekToPreviousMediaItem()
            "seek" -> value?.let { seek(c, (it * 1000).toLong()) }
            "jump" -> value?.let { if (it.toInt() in 0 until c.mediaItemCount) { c.seekTo(it.toInt(), 0); c.play() } }
            "move" -> if (value != null && to != null) c.moveMediaItem(value.toInt(), to)
            "remove" -> value?.let { if (it.toInt() != c.currentMediaItemIndex) c.removeMediaItem(it.toInt()) }
            "volume" -> value?.let { c.volume = it.toFloat().coerceIn(0f, 1f) }
            "shuffle" -> c.shuffleModeEnabled = !c.shuffleModeEnabled
            "stop" -> { c.stop(); c.clearMediaItems(); Streams.all.clear() }
        }
    }

    /** A converted track seeks through the service's player (Streams.SEEK); anything else seeks as usual. */
    private fun seek(c: MediaController, ms: Long) {
        if (Streams.all[c.currentMediaItem?.mediaId]?.transcode == true) {
            c.sendCustomCommand(SessionCommand(Streams.SEEK, Bundle.EMPTY), Bundle().apply { putLong("ms", ms) })
        } else c.seekTo(ms)
    }

    fun pause() {
        controller?.pause()
    }

    fun state(): JSONObject {
        val c = controller ?: return JSONObject().put("ready", false)
        val ids = JSONArray()
        for (i in 0 until c.mediaItemCount) ids.put(c.getMediaItemAt(i).mediaId)
        val dur = c.duration
        return JSONObject().put("ready", true).put("playing", c.isPlaying).put("index", c.currentMediaItemIndex)
            .put("position", c.currentPosition / 1000.0).put("duration", if (dur > 0) dur / 1000.0 else JSONObject.NULL)
            .put("shuffle", c.shuffleModeEnabled).put("queue", ids).put("volume", c.volume.toDouble())
            .put("error", c.playerError?.let { "This track couldn't be played." } ?: JSONObject.NULL)
    }

    fun release() {
        main.removeCallbacks(ticker)
        MediaController.releaseFuture(future)
    }
}

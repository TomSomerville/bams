package media.bams.phone

import android.content.ComponentName
import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executor

/** The Downloads pages' remote for MusicService: play a queue of downloaded tracks, pause, skip, seek. */
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

    /** [tracks]: each {sid, id, path, title, artist, album, art (a local file), start, end}; seconds. */
    fun play(tracks: JSONArray, index: Int, shuffle: Boolean) {
        val c = controller ?: return
        val items = (0 until tracks.length()).map { i ->
            val t = tracks.getJSONObject(i)
            val uri = Uri.fromFile(File(t.getString("path")))
            val meta = MediaMetadata.Builder().setTitle(t.str("title")).setArtist(t.str("artist"))
                .setAlbumTitle(t.str("album")).setIsPlayable(true)
            t.str("art")?.let { if (File(it).exists()) meta.setArtworkUri(Uri.fromFile(File(it))) }
            val clip = MediaItem.ClippingConfiguration.Builder()
            if (!t.isNull("start")) clip.setStartPositionMs((t.getDouble("start") * 1000).toLong())
            if (!t.isNull("end")) clip.setEndPositionMs((t.getDouble("end") * 1000).toLong())
            MediaItem.Builder()
                .setMediaId("${t.getString("sid")}|${t.getInt("id")}")
                .setUri(uri)
                .setRequestMetadata(MediaItem.RequestMetadata.Builder().setMediaUri(uri).build())
                .setMediaMetadata(meta.build())
                .setClippingConfiguration(clip.build())
                .build()
        }
        c.shuffleModeEnabled = shuffle
        c.setMediaItems(items, index.coerceIn(0, maxOf(0, items.size - 1)), 0)
        c.prepare()
        c.play()
    }

    fun command(cmd: String, value: Double?) {
        val c = controller ?: return
        when (cmd) {
            "toggle" -> if (c.isPlaying) c.pause() else c.play()
            "pause" -> c.pause()
            "next" -> c.seekToNextMediaItem()
            "prev" -> if (c.currentPosition > 3000) c.seekTo(0) else c.seekToPreviousMediaItem()
            "seek" -> value?.let { c.seekTo((it * 1000).toLong()) }
            "jump" -> value?.let { c.seekTo(it.toInt(), 0) }
            "shuffle" -> c.shuffleModeEnabled = !c.shuffleModeEnabled
            "stop" -> { c.stop(); c.clearMediaItems() }
        }
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
            .put("shuffle", c.shuffleModeEnabled).put("queue", ids)
    }

    fun release() {
        main.removeCallbacks(ticker)
        MediaController.releaseFuture(future)
    }
}

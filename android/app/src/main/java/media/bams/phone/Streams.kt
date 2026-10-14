package media.bams.phone

import android.net.Uri
import androidx.annotation.OptIn
import androidx.media3.common.C
import androidx.media3.common.ForwardingPlayer
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import java.util.Collections
import java.util.Locale

/**
 * Music streamed from a server (web/src/music.tsx AppMusicProvider → Music.stream), by queue key. Most tracks are the
 * original file (seekable, a CUE track clipped out of it). A track the server converts (`transcode`,
 * /api/files/{id}/audio?t=) is a stream that can't seek: seeking asks for it again from there and its clock counts
 * from that point (`offset`). A file the phone turns out not to decode goes over to the conversion (`fallback`).
 */
object Streams {
    data class Stream(
        val key: String, val url: String, val transcode: Boolean, val fallback: String?, val start: Double,
        val end: Double?, val duration: Double?, val offset: Double, val meta: MediaMetadata,
    )

    val all: MutableMap<String, Stream> = Collections.synchronizedMap(mutableMapOf())

    /** A seek sent as a session command (args: "ms"): a controller drops a plain seek in a stream ExoPlayer told it
     *  can't seek, so the app's page seeks converted tracks this way (the lock screen asks the player directly). */
    const val SEEK = "media.bams.phone.SEEK"

    fun build(id: String, uri: Uri, meta: MediaMetadata, start: Double?, end: Double?): MediaItem {
        val clip = MediaItem.ClippingConfiguration.Builder()
        if (start != null) clip.setStartPositionMs((start * 1000).toLong())
        if (end != null) clip.setEndPositionMs((end * 1000).toLong())
        return MediaItem.Builder()
            .setMediaId(id)
            .setUri(uri)
            .setRequestMetadata(MediaItem.RequestMetadata.Builder().setMediaUri(uri).build())  // MusicService puts it back
            .setMediaMetadata(meta)
            .setClippingConfiguration(clip.build())
            .build()
    }

    /** A track's media item, `from` seconds into it: a converted stream starts there; a file is clipped to the track. */
    fun item(s: Stream, from: Double = 0.0): MediaItem =
        if (s.transcode) {
            val at = s.start + from
            build(s.key, Uri.parse("${s.url}?t=${"%.2f".format(Locale.ROOT, at)}"), s.meta, null, s.end?.let { it - at })
        } else build(s.key, Uri.parse(s.url), s.meta, s.start.takeIf { it > 0 }, s.end)

    /**
     * The service's player as everyone sees it (the page, the lock screen, headphones): a converted stream seeks by
     * starting over from there, and shows its time in the track and the track's length.
     */
    @OptIn(UnstableApi::class)
    class Player(private val p: androidx.media3.common.Player) : ForwardingPlayer(p) {
        init {
            p.addListener(object : androidx.media3.common.Player.Listener {
                override fun onPlayerError(error: PlaybackException) {
                    val s = current() ?: return
                    val fallback = s.fallback ?: return
                    if (s.transcode) return
                    // the phone can't decode it as it is: the server's conversion, from where it was
                    restart(s.copy(transcode = true, url = fallback, fallback = null), p.currentMediaItemIndex, p.currentPosition / 1000.0)
                }

                override fun onMediaItemTransition(item: MediaItem?, reason: Int) {
                    // back to a converted track that was seeked: from its start again
                    val s = all[item?.mediaId] ?: return
                    if (s.transcode && s.offset != 0.0 && reason != androidx.media3.common.Player.MEDIA_ITEM_TRANSITION_REASON_PLAYLIST_CHANGED) {
                        restart(s, p.currentMediaItemIndex, 0.0)
                    }
                }
            })
        }

        private fun current(): Stream? = all[p.currentMediaItem?.mediaId]

        private fun restart(s: Stream, index: Int, at: Double) {
            all[s.key] = s.copy(offset = at)
            p.replaceMediaItem(index, item(all[s.key]!!, at))
            // the new stream starts at `at` itself: play it from its own start (ExoPlayer would keep the old position)
            p.seekTo(index, 0)
            p.prepare()
            p.play()
        }

        override fun seekTo(positionMs: Long) = seekTo(p.currentMediaItemIndex, positionMs)

        override fun seekTo(mediaItemIndex: Int, positionMs: Long) {
            val s = if (mediaItemIndex in 0 until p.mediaItemCount) all[p.getMediaItemAt(mediaItemIndex).mediaId] else null
            if (s != null && s.transcode) restart(s, mediaItemIndex, maxOf(0L, positionMs) / 1000.0)
            else super.seekTo(mediaItemIndex, positionMs)
        }

        private fun offsetMs(): Long = current()?.takeIf { it.transcode }?.let { (it.offset * 1000).toLong() } ?: 0L

        override fun getCurrentPosition(): Long = super.getCurrentPosition() + offsetMs()
        override fun getContentPosition(): Long = super.getContentPosition() + offsetMs()
        override fun getBufferedPosition(): Long = super.getBufferedPosition() + offsetMs()

        override fun getDuration(): Long {
            val s = current()
            if (s != null && s.transcode) {
                val d = s.duration ?: s.end?.let { it - s.start }
                return d?.let { (it * 1000).toLong() } ?: C.TIME_UNSET
            }
            return super.getDuration()
        }

        override fun getContentDuration(): Long = duration

        // ExoPlayer takes a stream it can't seek in, of unknown length, for a live one: Media3 then hides its position,
        // the lock screen's seek bar and "previous". A converted track isn't live, and seeks by starting over.
        override fun isCurrentMediaItemLive(): Boolean = if (current()?.transcode == true) false else super.isCurrentMediaItemLive()
        override fun isCurrentMediaItemSeekable(): Boolean = current()?.transcode == true || super.isCurrentMediaItemSeekable()
        override fun isCurrentMediaItemDynamic(): Boolean = if (current()?.transcode == true) false else super.isCurrentMediaItemDynamic()

        override fun isCommandAvailable(command: Int): Boolean = availableCommands.contains(command)

        override fun getAvailableCommands(): androidx.media3.common.Player.Commands {
            val c = super.getAvailableCommands()
            return if (current()?.transcode == true)
                c.buildUpon().add(COMMAND_SEEK_IN_CURRENT_MEDIA_ITEM).add(COMMAND_SEEK_TO_PREVIOUS).build()
            else c
        }

        // ExoPlayer would seek the stream itself here: go through seekTo
        override fun seekToPrevious() {
            val s = current()
            if (s != null && s.transcode && (currentPosition > maxSeekToPreviousPosition || !hasPreviousMediaItem())) seekTo(0)
            else super.seekToPrevious()
        }
    }
}

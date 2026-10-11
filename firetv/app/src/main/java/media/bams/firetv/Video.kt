package media.bams.firetv

import android.content.Context
import android.os.Handler
import android.os.Looper
import androidx.annotation.OptIn
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.extractor.DefaultExtractorsFactory
import androidx.media3.ui.PlayerView
import org.json.JSONObject

/**
 * The video player: ExoPlayer drawing into [view], which sits under the app's see-through WebView (like AVPlay's
 * video plane under the page on a Samsung TV). The page drives it through [Bridge] and hears back through [send]
 * (firetv.ts `FirePlayerEvent`). Main thread only. One ExoPlayer per load, released on stop: decoders are freed
 * between videos and nothing of the last stream lingers.
 */
@OptIn(UnstableApi::class)
class Video(private val context: Context, private val view: PlayerView, private val userAgent: String,
            private val send: (JSONObject) -> Unit) {
    private var player: ExoPlayer? = null
    private var loadId = 0
    private var readySent = false
    private val main = Handler(Looper.getMainLooper())
    // the position, 4 times a second: the page draws text subtitles from it
    private val tick = object : Runnable {
        override fun run() {
            report()
            main.postDelayed(this, 250)
        }
    }

    private val listener = object : Player.Listener {
        override fun onPlaybackStateChanged(state: Int) {
            when (state) {
                Player.STATE_BUFFERING -> send(event("buffering").put("on", true))
                Player.STATE_READY -> {
                    send(event("buffering").put("on", false))
                    if (!readySent) {
                        readySent = true
                        send(event("ready"))
                    }
                }
                Player.STATE_ENDED -> {
                    report()
                    send(event("ended"))
                }
                else -> Unit
            }
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            view.keepScreenOn = isPlaying
            report()
        }

        override fun onPlayerError(error: PlaybackException) {
            send(event("error").put("message", "${error.errorCodeName}: ${error.message ?: ""}".trimEnd(' ', ':')))
        }
    }

    /** Every event carries the page's id for the load it belongs to: one sent just before a reload is ignored. */
    private fun event(type: String) = JSONObject().put("type", type).put("id", loadId)

    /** Play [url] from [startMs]. [hls]: a BAMS HLS session playlist (its ticket URL doesn't end in .m3u8). */
    fun load(url: String, startMs: Long, hls: Boolean, id: Int) {
        stop()
        loadId = id
        // a converted segment can take a while: the server makes it when it's asked for
        val http = DefaultHttpDataSource.Factory()
            .setUserAgent(userAgent)
            .setConnectTimeoutMs(15_000)
            .setReadTimeoutMs(60_000)
            .setAllowCrossProtocolRedirects(true)
        // files without an index (some TS, MP3) still seek, by bitrate
        val extractors = DefaultExtractorsFactory().setConstantBitrateSeekingEnabled(true)
        val p = ExoPlayer.Builder(context, DefaultRenderersFactory(context).setEnableDecoderFallback(true))
            .setMediaSourceFactory(DefaultMediaSourceFactory(DefaultDataSource.Factory(context, http), extractors))
            .setAudioAttributes(
                AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MOVIE).build(),
                true,
            )
            .build()
        p.addListener(listener)
        view.player = p
        val item = MediaItem.Builder().setUri(url)
        if (hls) item.setMimeType(MimeTypes.APPLICATION_M3U8)
        p.setMediaItem(item.build(), startMs)
        p.prepare()
        p.playWhenReady = true
        player = p
        readySent = false
        main.post(tick)
    }

    fun play() {
        player?.let {
            if (it.playbackState == Player.STATE_ENDED) it.seekTo(0)
            it.playWhenReady = true
        }
    }

    fun pause() {
        player?.playWhenReady = false
    }

    fun seek(ms: Long) {
        player?.seekTo(maxOf(0, ms))
    }

    /** Switch to the file's n-th audio track (the order the server lists them in). False if there's no such track
     *  or this device can't decode it: the page then asks the server for a stream with it. */
    fun selectAudio(n: Int): Boolean {
        val p = player ?: return false
        val group = p.currentTracks.groups.filter { it.type == C.TRACK_TYPE_AUDIO }.getOrNull(n) ?: return false
        if (!group.isSupported) return false
        p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
            .setOverrideForType(TrackSelectionOverride(group.mediaTrackGroup, 0))
            .build()
        return true
    }

    fun stop() {
        main.removeCallbacks(tick)
        player?.let {
            it.removeListener(listener)
            it.release()
        }
        player = null
        view.player = null
        view.keepScreenOn = false
    }

    private fun report() {
        val p = player ?: return
        val d = p.duration
        send(event("time")
            .put("t", p.currentPosition / 1000.0)
            .put("d", if (d == C.TIME_UNSET || d <= 0) JSONObject.NULL else d / 1000.0)
            .put("paused", !p.playWhenReady || p.playbackState == Player.STATE_ENDED))
    }
}

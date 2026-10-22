package media.bams.firetv

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import androidx.annotation.OptIn
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.common.Tracks
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
 *
 * In the background (Home, another app, the TV asleep) the player is released too ([park]) and made again, paused at
 * the same place, when the app comes back ([unpark]). Kept paused, it held the device's one Dolby output through a day
 * of standby, and the next videos' sound never started (Fire TV smart TV, 2026-10-21).
 */
@OptIn(UnstableApi::class)
class Video(private val context: Context, private val view: PlayerView, private val userAgent: String,
            private val send: (JSONObject) -> Unit) {
    private var player: ExoPlayer? = null
    private var loadId = 0
    private var readySent = false
    private val main = Handler(Looper.getMainLooper())

    /** What's playing, to make the player again after [park]. */
    private class Stream(val url: String, val hls: Boolean)
    private var stream: Stream? = null
    private var parked: Long? = null  // the position while released in the background
    private var audioPick: Int? = null     // the audio track the page chose (selectAudio), kept for a remade player
    private var pendingAudio: Int? = null  // ... chosen again once the remade player knows its tracks

    // the stall watch: when the position last moved while playing, and whether this load's stall was told
    private var lastPos = -1L
    private var movedAt = 0L
    private var stallSent = false

    // the position, 4 times a second: the page draws text subtitles from it
    private val tick = object : Runnable {
        override fun run() {
            report()
            watch()
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

        override fun onTracksChanged(tracks: Tracks) {
            val n = pendingAudio ?: return
            pendingAudio = null
            selectAudio(n)
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
        stream = Stream(url, hls)
        readySent = false
        audioPick = null
        pendingAudio = null
        open(url, startMs, hls, true)
    }

    private fun open(url: String, startMs: Long, hls: Boolean, play: Boolean) {
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
        // the page draws text subtitles (the server's WebVTT, with Off and the timing control) and has the server
        // burn in picture ones: ExoPlayer must show none of its own, or a file's "default" subtitle track (or one
        // matching the system's caption setting) stays on screen whatever the page's menu says
        p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
            .setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true)
            .build()
        p.addListener(listener)
        view.player = p
        val item = MediaItem.Builder().setUri(url)
        if (hls) item.setMimeType(MimeTypes.APPLICATION_M3U8)
        p.setMediaItem(item.build(), startMs)
        p.prepare()
        p.playWhenReady = play
        player = p
        lastPos = -1
        stallSent = false
        main.post(tick)
    }

    /** The app went to the background: release the player (and the device's decoders and sound output), keeping the
     *  place. The page hears it as paused there. */
    fun park() {
        val p = player ?: return
        val at = p.currentPosition
        send(event("time").put("t", at / 1000.0).put("d", duration(p)).put("paused", true))
        release()
        parked = at
    }

    /** Back in front: the player again, paused where it was (the page's Play goes on). */
    fun unpark() {
        val at = parked ?: return
        val s = stream ?: return
        parked = null
        pendingAudio = audioPick
        open(s.url, at, s.hls, false)
    }

    fun play() {
        unpark()
        player?.let {
            if (it.playbackState == Player.STATE_ENDED) it.seekTo(0)
            it.playWhenReady = true
        }
    }

    fun pause() {
        player?.playWhenReady = false
    }

    fun seek(ms: Long) {
        if (parked != null) parked = maxOf(0, ms)
        player?.seekTo(maxOf(0, ms))
    }

    /** Playing, but the position hasn't moved for [STALL_MS]: the page falls back (once per load). Seen when the
     *  device's Dolby output was stuck: the picture came, the sound (which drives the clock) never started. Buffering
     *  and pauses don't count; a seek starts the wait again. */
    private fun watch() {
        val p = player ?: return
        val now = SystemClock.elapsedRealtime()
        val pos = p.currentPosition
        if (!p.isPlaying || pos != lastPos) {
            lastPos = pos
            movedAt = now
        } else if (!stallSent && now - movedAt > STALL_MS) {
            stallSent = true
            send(event("stalled").put("t", pos / 1000.0))
        }
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
        audioPick = n
        return true
    }

    fun stop() {
        release()
        stream = null
        parked = null
    }

    private fun release() {
        main.removeCallbacks(tick)
        player?.let {
            it.removeListener(listener)
            it.release()
        }
        player = null
        view.player = null
        view.keepScreenOn = false
    }

    private fun duration(p: ExoPlayer): Any {
        val d = p.duration
        return if (d == C.TIME_UNSET || d <= 0) JSONObject.NULL else d / 1000.0
    }

    private fun report() {
        val p = player ?: return
        send(event("time")
            .put("t", p.currentPosition / 1000.0)
            .put("d", duration(p))
            .put("paused", !p.playWhenReady || p.playbackState == Player.STATE_ENDED))
    }

    private companion object {
        const val STALL_MS = 8_000L
    }
}

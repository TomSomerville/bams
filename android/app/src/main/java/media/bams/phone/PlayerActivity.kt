package media.bams.phone

import android.app.Activity
import android.app.PictureInPictureParams
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Rational
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.TextView
import androidx.annotation.OptIn
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Plays downloaded movies and episodes from the phone's storage, with ExoPlayer: the original file as it is (Android's
 * own decoders; a sound track the phone can't decode is passed over for one it can). Subtitles downloaded with the
 * file are offered too. Where you stop is kept (Progress) and sent to the server later. Episodes play on into the
 * next downloaded one.
 */
@OptIn(UnstableApi::class)
class PlayerActivity : Activity() {
    private lateinit var player: ExoPlayer
    private lateinit var view: PlayerView
    private lateinit var title: TextView
    private lateinit var queue: JSONArray
    private val ticker = Handler(Looper.getMainLooper())
    private val app get() = application as App

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        queue = JSONArray(intent.getStringExtra(QUEUE) ?: "[]")
        val start = intent.getIntExtra(INDEX, 0)

        player = ExoPlayer.Builder(this).setHandleAudioBecomingNoisy(true).build()
        view = PlayerView(this).apply {
            player = this@PlayerActivity.player
            setShowSubtitleButton(true)
            setShowNextButton(queue.length() > 1)
            setShowPreviousButton(queue.length() > 1)
            setShutterBackgroundColor(Color.BLACK)
            keepScreenOn = true
        }
        title = TextView(this).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            setShadowLayer(6f, 0f, 1f, Color.BLACK)
            setPadding(dp(20), dp(16), dp(20), dp(16))
            gravity = Gravity.START
        }
        view.setControllerVisibilityListener(PlayerView.ControllerVisibilityListener { v -> title.visibility = v })
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        root.addView(view, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        root.addView(title, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP))
        setContentView(root)
        immersive()

        val items = (0 until queue.length()).map { item(queue.getJSONObject(it)) }
        player.setMediaItems(items, start, resumeAt(queue.getJSONObject(start)))
        player.addListener(object : Player.Listener {
            override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) {
                showTitle()
                if (reason == Player.MEDIA_ITEM_TRANSITION_REASON_AUTO) {
                    // the one before ended: watched
                    val prev = player.previousMediaItemIndex
                    if (prev != C.INDEX_UNSET) finished(queue.getJSONObject(prev))
                }
            }

            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) {
                    finished(queue.getJSONObject(player.currentMediaItemIndex))
                    finish()
                }
            }

            override fun onPlayerError(error: PlaybackException) {
                title.visibility = View.VISIBLE
                title.text = "Can't play this on this phone: ${error.errorCodeName.removePrefix("ERROR_CODE_").lowercase().replace('_', ' ')}"
            }
        })
        player.prepare()
        player.play()
        showTitle()
        ticker.postDelayed(object : Runnable {
            override fun run() {
                if (player.isPlaying) save()
                ticker.postDelayed(this, 10_000)
            }
        }, 10_000)
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun showTitle() {
        val q = queue.optJSONObject(player.currentMediaItemIndex) ?: return
        title.text = listOfNotNull(q.str("title"), q.str("sub")).joinToString("  ·  ")
    }

    private fun item(q: JSONObject): MediaItem {
        val subs = q.optJSONArray("subs") ?: JSONArray()
        val configs = (0 until subs.length()).map { subs.getJSONObject(it) }.filter { File(it.getString("path")).exists() }.map { s ->
            MediaItem.SubtitleConfiguration.Builder(Uri.fromFile(File(s.getString("path"))))
                .setMimeType(MimeTypes.TEXT_VTT)
                .setLanguage(s.str("language"))
                .setLabel(s.str("label"))
                .setSelectionFlags(if (s.optBoolean("forced")) C.SELECTION_FLAG_FORCED else 0)
                .build()
        }
        return MediaItem.Builder()
            .setUri(Uri.fromFile(File(q.getString("path"))))
            .setMediaId("${q.getString("sid")}|${q.getInt("id")}")
            .setSubtitleConfigurations(configs)
            .build()
    }

    /** Where to start: where you stopped (on the phone, else as the server had it), unless it was finished. */
    private fun resumeAt(q: JSONObject): Long {
        val p = app.progress.get(q.getString("sid"), q.getInt("id"))
        val pos = p?.optDouble("position") ?: q.optDouble("position", 0.0)
        val dur = p?.optDouble("duration") ?: q.optDouble("duration", 0.0)
        if (pos.isNaN() || pos < 30 || (dur > 0 && pos > dur * 0.95)) return 0
        return (pos * 1000).toLong()
    }

    private fun save() {
        val q = queue.optJSONObject(player.currentMediaItemIndex) ?: return
        val dur = player.duration.takeIf { it != C.TIME_UNSET }?.let { it / 1000.0 }
        app.progress.record(q.getString("sid"), q.getInt("id"), player.currentPosition / 1000.0, dur)
    }

    private fun finished(q: JSONObject) {
        val dur = player.duration.takeIf { it != C.TIME_UNSET }?.let { it / 1000.0 } ?: q.optDouble("duration", 0.0)
        if (dur > 0) app.progress.record(q.getString("sid"), q.getInt("id"), dur, dur)
    }

    private fun immersive() {
        if (Build.VERSION.SDK_INT >= 30) {
            window.insetsController?.let {
                it.hide(WindowInsets.Type.systemBars())
                it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = (View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN)
        }
    }

    // Home while playing: carry on in a small window
    override fun onUserLeaveHint() {
        if (player.isPlaying && Build.VERSION.SDK_INT >= 26) {
            try {
                enterPictureInPictureMode(PictureInPictureParams.Builder().setAspectRatio(Rational(16, 9)).build())
            } catch (e: Exception) { /* not allowed on this phone */ }
        }
    }

    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean, newConfig: android.content.res.Configuration) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        view.useController = !isInPictureInPictureMode
        title.visibility = if (isInPictureInPictureMode) View.GONE else title.visibility
    }

    override fun onStop() {
        save()
        if (!isInPictureInPictureMode) player.pause()
        super.onStop()
    }

    override fun onDestroy() {
        ticker.removeCallbacksAndMessages(null)
        save()
        player.release()
        app.emit("progress")
        super.onDestroy()
    }

    companion object {
        const val QUEUE = "queue"
        const val INDEX = "index"

        /** Play [queue] (each: sid, id, title, sub, path, subs[{path,label,language,forced}], position, duration). */
        fun start(context: Context, queue: JSONArray, index: Int) {
            context.startActivity(Intent(context, PlayerActivity::class.java)
                .putExtra(QUEUE, queue.toString()).putExtra(INDEX, index))
        }
    }
}

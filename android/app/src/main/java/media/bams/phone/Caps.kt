package media.bams.phone

import androidx.annotation.OptIn
import androidx.media3.common.MimeTypes
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.mediacodec.MediaCodecUtil
import org.json.JSONArray
import org.json.JSONObject

/**
 * What this phone decodes, in BAMS's probe names ("AAC", "AC3", "HEVC"), read from Android's decoders (phones
 * differ: Dolby sound depends on the maker). The web UI warns before downloading a file whose sound this phone
 * can't play offline (android.ts `unplayableAudio`); online the server converts it.
 */
@OptIn(UnstableApi::class)
object Caps {
    private val VIDEO = listOf(
        "H.264" to MimeTypes.VIDEO_H264, "HEVC" to MimeTypes.VIDEO_H265, "VP9" to MimeTypes.VIDEO_VP9,
        "AV1" to MimeTypes.VIDEO_AV1, "VP8" to MimeTypes.VIDEO_VP8, "MPEG-2" to MimeTypes.VIDEO_MPEG2,
        "MPEG-4" to MimeTypes.VIDEO_MP4V, "VC-1" to MimeTypes.VIDEO_VC1,
    )
    private val AUDIO = listOf(
        "AAC" to MimeTypes.AUDIO_AAC, "MP3" to MimeTypes.AUDIO_MPEG, "MP2" to MimeTypes.AUDIO_MPEG_L2,
        "FLAC" to MimeTypes.AUDIO_FLAC, "Opus" to MimeTypes.AUDIO_OPUS, "Vorbis" to MimeTypes.AUDIO_VORBIS,
        "AC3" to MimeTypes.AUDIO_AC3, "EAC3" to MimeTypes.AUDIO_E_AC3, "DTS" to MimeTypes.AUDIO_DTS,
        "TrueHD" to MimeTypes.AUDIO_TRUEHD, "ALAC" to MimeTypes.AUDIO_ALAC,
    )

    private fun has(mime: String): Boolean =
        try { MediaCodecUtil.getDecoderInfos(mime, false, false).isNotEmpty() } catch (e: Exception) { false }

    private var cached: JSONObject? = null

    fun json(): JSONObject = cached ?: JSONObject()
        .put("audio", JSONArray(listOf("PCM") + AUDIO.filter { has(it.second) }.map { it.first }))  // ExoPlayer plays PCM itself
        .put("video", JSONArray(VIDEO.filter { has(it.second) }.map { it.first }))
        .also { cached = it }
}

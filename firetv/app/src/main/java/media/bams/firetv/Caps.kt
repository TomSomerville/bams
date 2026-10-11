package media.bams.firetv

import android.content.Context
import android.media.MediaCodecInfo.CodecProfileLevel
import androidx.annotation.OptIn
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MimeTypes
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.audio.AudioCapabilities
import androidx.media3.exoplayer.mediacodec.MediaCodecInfo
import androidx.media3.exoplayer.mediacodec.MediaCodecUtil
import org.json.JSONArray
import org.json.JSONObject

/**
 * What this Fire TV plays, for the TV app's `plan.ts` (firetv.ts `FireCaps`), in BAMS's probe names ("HEVC", "EAC3").
 * Fire TV models differ a lot: a 1080p stick takes no 4K, only some decode AV1, Dolby sound may only go to an AV
 * receiver as-is. So it's read from Android's decoders and the audio output, not from a table.
 */
@OptIn(UnstableApi::class)
object Caps {
    /** probe name -> MIME type, and whether a software decoder counts (too slow for these on a TV's CPU) */
    private val VIDEO = listOf(
        Triple("H.264", MimeTypes.VIDEO_H264, true),
        Triple("HEVC", MimeTypes.VIDEO_H265, false),
        Triple("VP9", MimeTypes.VIDEO_VP9, false),
        Triple("AV1", MimeTypes.VIDEO_AV1, false),
        Triple("VP8", MimeTypes.VIDEO_VP8, true),
        Triple("MPEG-2", MimeTypes.VIDEO_MPEG2, true),
        Triple("MPEG-4", MimeTypes.VIDEO_MP4V, true),
        Triple("VC-1", MimeTypes.VIDEO_VC1, false),
    )

    /** probe name -> MIME type, and the encoding that can go to the TV/receiver as-is (passthrough), if any */
    private val AUDIO = listOf(
        Triple("AAC", MimeTypes.AUDIO_AAC, null),
        Triple("MP3", MimeTypes.AUDIO_MPEG, null),
        Triple("MP2", MimeTypes.AUDIO_MPEG_L2, null),
        Triple("FLAC", MimeTypes.AUDIO_FLAC, null),
        Triple("Opus", MimeTypes.AUDIO_OPUS, null),
        Triple("Vorbis", MimeTypes.AUDIO_VORBIS, null),
        Triple("AC3", MimeTypes.AUDIO_AC3, C.ENCODING_AC3),
        Triple("EAC3", MimeTypes.AUDIO_E_AC3, C.ENCODING_E_AC3),
        Triple("DTS", MimeTypes.AUDIO_DTS, C.ENCODING_DTS),
        Triple("TrueHD", MimeTypes.AUDIO_TRUEHD, C.ENCODING_DOLBY_TRUEHD),
    )

    private fun decoders(mime: String): List<MediaCodecInfo> =
        try {
            MediaCodecUtil.getDecoderInfos(mime, false, false)
        } catch (e: MediaCodecUtil.DecoderQueryException) {
            emptyList()
        }

    fun json(context: Context): JSONObject {
        val video = JSONObject()
        for ((name, mime, softwareOk) in VIDEO) {
            val usable = decoders(mime).filter { softwareOk || !it.softwareOnly }
            var w = 0
            var h = 0
            for (d in usable) {
                val vc = d.capabilities?.videoCapabilities ?: continue
                w = maxOf(w, vc.supportedWidths.upper)
                h = maxOf(h, vc.supportedHeights.upper)
            }
            if (usable.isNotEmpty()) video.put(name, JSONObject().put("w", if (w > 0) w else 1920).put("h", if (h > 0) h else 1080))
        }

        val out = AudioCapabilities.getCapabilities(context, AudioAttributes.DEFAULT, null)
        val audio = JSONArray().put("PCM")  // ExoPlayer plays raw PCM itself
        for ((name, mime, passthrough) in AUDIO) {
            if (decoders(mime).isNotEmpty() || (passthrough != null && out.supportsEncoding(passthrough))) audio.put(name)
        }

        val profiles = { mime: String -> decoders(mime).flatMap { it.capabilities?.profileLevels?.asList() ?: emptyList() } }
        return JSONObject()
            .put("video", video)
            .put("audio", audio)
            .put("h264HighBit", profiles(MimeTypes.VIDEO_H264).any { it.profile == CodecProfileLevel.AVCProfileHigh10 })
            .put("dvProfile5", profiles(MimeTypes.VIDEO_DOLBY_VISION).any { it.profile == CodecProfileLevel.DolbyVisionProfileDvheStn })
    }
}

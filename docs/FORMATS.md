# Media formats

Every video and audio format BAMS knows about: whether it's **indexed** (found by a scan), whether
**browsers** can play it as-is, and what the **server** does about it.

**How playback is decided** (`server/bams/stream.py`):

| Method | When | What the server does |
|---|---|---|
| **Direct Play** | MP4 + H.264 + browser-friendly audio | Sends the original file (HTTP Range, so seeking works) |
| **Direct Stream: file** | Browser-friendly video *and* audio in MKV/WebM/MP4 | Sends the original file; Chrome/Edge open MKV fine |
| **Direct Stream: remux** | Browser-friendly video, but audio browsers can't decode, or a container they can't open | FFmpeg **copies the video** and **converts the audio to AAC**, streamed as fragmented MP4. Little CPU, no video quality loss |
| **Transcode** | The video codec itself isn't browser-friendly (or the browser says it can't decode HEVC/AV1/VP9), or the viewer picked a lower quality | FFmpeg **re-encodes the video to H.264** (GPU: NVENC / QSV / AMF / VAAPI, else x264; GPU decoding too) and the audio to AAC, served as **HLS** (4 s segments made on demand, so seeking is native; plain fragmented MP4 for browsers without HLS). Deinterlaces, fixes anamorphic pixels, tone-maps HDR |

Legend: ✅ yes · ⚠️ depends (hardware, OS or browser version) · ❌ no · 🔜 planned

Browser columns are the current desktop browsers: **Chromium** (Chrome/Edge), **Firefox**, **Safari**.
The server only *reads* media files, whatever the format ([READ-ONLY.md](READ-ONLY.md)).

---

## 1. Video containers (file types)

| Container | Extensions | Indexed | Chromium | Firefox | Safari | BAMS today |
|---|---|---|---|---|---|---|
| MP4 / MPEG-4 Part 14 | `.mp4` `.m4v` | ✅ | ✅ | ✅ | ✅ | Direct Play / Stream |
| QuickTime | `.mov` | ✅ | ✅ (H.264/AAC inside) | ⚠️ | ✅ | Direct Stream (treated as MP4) |
| Matroska | `.mkv` | ✅ | ✅ | ⚠️ (newer versions) | ❌ | Direct Stream (file); remux if audio needs converting |
| WebM | `.webm` | ✅ | ✅ | ✅ | ⚠️ | Direct Stream |
| AVI | `.avi` `.divx` | ✅ | ❌ | ❌ | ❌ | Remux to MP4 if the codecs are copyable; else transcode |
| MPEG transport stream | `.ts` `.m2ts` `.mts` | ✅ | ❌ | ❌ | ❌ (only via HLS) | Remux to MP4 |
| MPEG program stream | `.mpg` `.mpeg` `.mpe` | ✅ | ❌ | ❌ | ❌ | Usually MPEG-2 video: transcode |
| Windows Media / ASF | `.wmv` `.asf` | ✅ | ❌ | ❌ | ❌ | Transcode (VC-1/WMV video) |
| Windows Media Center TV | `.wtv` `.dvr-ms` | ✅ | ❌ | ❌ | ❌ | Remux (H.264) or Transcode (MPEG-2) |
| Flash Video | `.flv` `.f4v` | ✅ | ❌ | ❌ | ❌ | Remux if H.264; else transcode |
| Ogg video | `.ogv` | ✅ | ⚠️ (Theora dropped) | ✅ | ❌ | Transcode (Theora) |
| 3GPP (old phones) | `.3gp` `.3g2` | ✅ | ⚠️ | ⚠️ | ✅ | Remux / transcode |
| RealMedia | `.rm` `.rmvb` | ✅ | ❌ | ❌ | ❌ | Transcode to H.264 |
| DVD / Blu-ray image | `.iso` | ✅ (as a file) | ❌ | ❌ | ❌ | 🔜 phase 3 (main title via FFmpeg `dvdvideo` / libbluray); encrypted discs out of scope |
| DVD folder | `VIDEO_TS/*.VOB` | ❌ | ❌ | ❌ | ❌ | 🔜 with ISO support |
| Blu-ray folder | `BDMV/STREAM/*.m2ts` | ❌ | ❌ | ❌ | ❌ | 🔜 with ISO support |

## 2. Video codecs (inside those containers)

| Codec | Also known as | Chromium | Firefox | Safari | BAMS today |
|---|---|---|---|---|---|
| H.264 | AVC, x264 | ✅ | ✅ | ✅ | Copied as-is (8-bit 4:2:0; 10-bit "Hi10P", 4:2:2 and 4:4:4 are transcoded) |
| H.265 | HEVC, x265 | ⚠️ (Windows/Mac with hardware decode) | ⚠️ | ✅ | Copied as-is where the browser decodes it; transcoded to H.264 for browsers that can't (the player checks) |
| AV1 | | ✅ | ✅ | ⚠️ (newer Apple chips) | Copied as-is; transcoded for browsers that can't |
| VP9 | | ✅ | ✅ | ⚠️ | Copied as-is; transcoded for browsers that can't |
| VP8 | | ✅ | ✅ | ⚠️ | Copied as-is (WebM); transcoded if it would need a remux |
| MPEG-4 Part 2 | Xvid, DivX | ❌ | ❌ | ❌ | Transcode to H.264 |
| MPEG-2 | DVD, broadcast TV | ❌ | ❌ | ❌ | Transcode to H.264 |
| MPEG-1 | VCD | ❌ | ❌ | ❌ | Transcode to H.264 |
| VC-1 / WMV3 | Windows Media Video | ❌ | ❌ | ❌ | Transcode to H.264 |
| H.263 | | ❌ | ❌ | ❌ | Transcode to H.264 |
| Theora | | ❌ (removed) | ⚠️ | ❌ | Transcode to H.264 |
| ProRes | | ❌ | ❌ | ⚠️ (Mac) | Transcode to H.264 |
| DNxHD / DNxHR | | ❌ | ❌ | ❌ | Transcode to H.264 |
| Motion JPEG | MJPEG | ❌ | ❌ | ❌ | Transcode to H.264 |
| H.266 | VVC | ❌ | ❌ | ❌ | Transcode to H.264 |
| RealVideo | RV30/RV40 | ❌ | ❌ | ❌ | Transcode to H.264 |

**HDR** (HDR10, HLG, Dolby Vision): detected by ffprobe and shown. Played as-is where the device supports it.
When a file is **transcoded**, HDR10 and HLG are tone-mapped to SDR (BT.709, Hable curve) if FFmpeg has the `zscale` filter.
Dolby Vision goes through FFmpeg's `libplacebo` filter (needs Vulkan; tested once at startup), which applies the DV
metadata. That matters for **profile 5**, which has no HDR10 base layer and shows green/purple without it; the player
converts profile 5 for browsers that don't report Dolby Vision support (`dvh1`). Without libplacebo, Dolby Vision
falls back to the HDR10 tone-map (right for profile 8, wrong colours for profile 5). The profile is recorded by the
scan (`probe.dv_profile`; files probed before this have none).

## 3. Audio codecs inside video files

This is what decides "plays with sound" vs "plays silently" (the Bob's Burgers issue).

| Codec | Also known as | Chromium | Firefox | Safari | BAMS today |
|---|---|---|---|---|---|
| AAC | AAC-LC, HE-AAC | ✅ | ✅ | ✅ | Kept as-is |
| MP3 | MPEG-1 Layer III | ✅ | ✅ | ✅ | Kept as-is |
| Opus | | ✅ | ✅ | ⚠️ | Kept as-is |
| Vorbis | | ✅ | ✅ | ⚠️ | Kept as-is |
| FLAC | | ✅ | ✅ | ✅ | Kept as-is |
| AC3 | Dolby Digital, DD 5.1 | ❌ | ❌ | ✅ | **Converted to AAC** (remux) |
| E-AC3 | Dolby Digital Plus, DD+, DDP, Atmos (lossy) | ❌ | ❌ | ✅ | **Converted to AAC** |
| DTS | DTS, DTS-ES | ❌ | ❌ | ❌ | **Converted to AAC** |
| DTS-HD MA / DTS:X | | ❌ | ❌ | ❌ | **Converted to AAC** |
| TrueHD | Dolby TrueHD, Atmos (lossless) | ❌ | ❌ | ❌ | **Converted to AAC** |
| PCM / LPCM | Blu-ray uncompressed | ⚠️ (in WAV only) | ⚠️ | ⚠️ | **Converted to AAC** |
| MP2 | MPEG-1 Layer II (broadcast) | ❌ | ❌ | ❌ | **Converted to AAC** |
| WMA | Windows Media Audio | ❌ | ❌ | ❌ | **Converted to AAC** |
| ALAC | Apple Lossless | ❌ | ❌ | ✅ | **Converted to AAC** |

Today the conversion is to **stereo AAC 192 kbps** (surround is downmixed). 🔜 5.1 AAC for surround-capable
clients, a track picker for files with several audio languages (the API already takes `?audio=`), and
pass-through for clients that decode Dolby (TV apps).

## 4. Subtitles

| Format | Type | Extensions / where | Browsers | BAMS |
|---|---|---|---|---|
| WebVTT | text | `.vtt` | ✅ native | 🔜 served as-is |
| SubRip | text | `.srt`, or embedded in MKV | ❌ | 🔜 convert to WebVTT |
| ASS / SSA | text, styled | `.ass` `.ssa`, embedded (anime) | ❌ | 🔜 WebVTT (styling lost), or burn in to keep styling |
| MP4 timed text | text | embedded in MP4 (`mov_text`) | ❌ | 🔜 convert to WebVTT |
| TTML / DFXP | text | `.ttml` `.dfxp` | ❌ | 🔜 convert to WebVTT |
| PGS | image | embedded in MKV/M2TS (Blu-ray) | ❌ | 🔜 burn in (needs video transcode) |
| VobSub | image | `.sub` + `.idx`, embedded (DVD) | ❌ | 🔜 burn in |
| DVB subtitles | image | embedded in TS (broadcast) | ❌ | 🔜 burn in |

Embedded subtitle tracks are already detected by ffprobe and listed in the file details. Sidecar files
(`Movie (2020).en.srt` next to the video) will be picked up when subtitle support lands.

## 5. Music (audio-only files)

Indexed in **Music** libraries (`config.AUDIO_EXTS`). Test albums are in `C:\Users\Beached\MyMusic`.
"Plays as-is" = the original file is streamed (seeking via HTTP Range). "Converted" = FFmpeg converts it to
**AAC 256 kbps stereo** (≤ 48 kHz) in fragmented MP4 while streaming (`/api/files/{id}/audio?t=`); seeking restarts
the conversion at the new point. The rule is `stream.BROWSER_AUDIO_FILES` (container + codec, from ffprobe).

| Format | Extensions | Lossless | Chromium | Firefox | Safari | BAMS today |
|---|---|---|---|---|---|---|
| MP3 | `.mp3` | | ✅ | ✅ | ✅ | Plays as-is |
| AAC | `.m4a` `.aac` | | ✅ | ✅ | ✅ | Plays as-is |
| ALAC (Apple Lossless) | `.m4a` | ✅ | ❌ | ❌ | ✅ | Converted |
| FLAC (incl. 24-bit / 96 kHz) | `.flac` | ✅ | ✅ | ✅ | ✅ | Plays as-is |
| Opus | `.opus` | | ✅ | ✅ | ⚠️ | Plays as-is |
| Ogg Vorbis / Ogg FLAC | `.ogg` `.oga` | | ✅ | ✅ | ⚠️ | Plays as-is |
| WAV (PCM) | `.wav` | ✅ | ✅ | ✅ | ✅ | Plays as-is (big files) |
| AIFF | `.aif` `.aiff` `.aifc` | ✅ | ❌ | ❌ | ✅ | Converted |
| WMA (incl. Pro / Lossless) | `.wma` | ⚠️ | ❌ | ❌ | ❌ | Converted |
| Monkey's Audio | `.ape` | ✅ | ❌ | ❌ | ❌ | Converted |
| WavPack | `.wv` | ✅ | ❌ | ❌ | ❌ | Converted |
| DSD | `.dsf` `.dff` | ✅ | ❌ | ❌ | ❌ | Converted (resampled to 48 kHz) |
| Matroska audio | `.mka` | depends | ❌ | ❌ | ❌ | Converted |
| AC3 / DTS files | `.ac3` `.dts` | | ❌ | ❌ | ⚠️ | Converted |
| MP2 | `.mp2` | | ❌ | ❌ | ❌ | Converted |
| CUE sheet + one big file | `.cue` + `.flac`/`.ape`/`.wav` | | n/a | n/a | n/a | 🔜 (the big file is indexed as one track today) |
| Playlists | `.m3u` `.m3u8` `.pls` | | n/a | n/a | n/a | 🔜 import as BAMS playlists |

Before ffprobe has seen a file, the extension decides (an `.m4a` is assumed AAC until probed). Without FFmpeg,
"Converted" files are sent as-is (best effort).

**Tags** are read by ffprobe (ID3v1/v2, Vorbis comments, MP4 atoms, APE, ASF), merged from the container and the
first audio stream (Ogg/Opus keep them on the stream) and normalised in `probe.music_tags`: title, artist, album,
album artist, track, disc, date, original date, genre, compilation, MusicBrainz ids. Without tags the folder layout
is used (`Artist/Album (Year)/01 - Title`, `CD1`/`Disc 2` folders, `Artist - Album` folders, FMA-style names).

**Artwork**: `cover`/`folder`/`front`/`album`/`albumart` `.jpg/.jpeg/.png/.webp` in the album folder (or its parent
for disc folders), else the picture embedded in a track (extracted by FFmpeg to a pipe); `artist`/`folder`/`poster`
images in the artist folder. Then, when music identification is on, the Cover Art Archive and Wikimedia Commons fill
what's still missing. Copies live in `data/images/music/`.

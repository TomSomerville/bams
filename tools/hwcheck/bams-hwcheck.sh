#!/usr/bin/env bash
# BAMS hardware check for Linux (Debian 12+, Ubuntu 24.04+, Mint 22+).
#
# Measures what BAMS leans on when it serves video: converting video (GPU or CPU), reading
# the media drive, the network link and memory. Run it on each machine you're considering
# (bams-hwcheck.ps1 on Windows runs the same tests and scores them the same way) and compare.
#
#   bash bams-hwcheck.sh [MEDIA_FOLDER_OR_FILE]
#
# It only reads your media. Test clips go in a temporary folder that's deleted at the end.
# The conversion tests need FFmpeg (sudo apt install ffmpeg). Takes about 1-5 minutes.
set -u

MEDIA="${1:-}"
VAAPI="${BAMS_VAAPI_DEVICE:-/dev/dri/renderD128}"
REPORT="$HOME/bams-hwcheck-$(hostname).txt"
TMP="$(mktemp -d -t bams-hwcheck.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
: > "$REPORT"

say()   { printf '%s\n' "$*" | tee -a "$REPORT"; }
calc()  { awk "BEGIN { printf \"%.1f\", $1 }"; }
floor() { awk "BEGIN { printf \"%d\", $1 }"; }
now()   { date +%s.%N; }
# points: value / full-marks value, capped at 1, times the weight
pts()   { awk "BEGIN { v = $1 / $2; if (v > 1) v = 1; if (v < 0) v = 0; printf \"%.1f\", v * $3 }"; }
NOTES=()

say "BAMS hardware check - $(hostname) - $(date '+%Y-%m-%d %H:%M')"
say ""

# ---- System ---------------------------------------------------------------------------------
. /etc/os-release 2>/dev/null
CPU=$(awk -F: '/model name/ { sub(/^ +/, "", $2); print $2; exit }' /proc/cpuinfo)
CORES=$(lscpu -p=SOCKET,CORE 2>/dev/null | grep -v '^#' | sort -u | wc -l)
THREADS=$(nproc)
RAM=$(awk '/MemTotal/ { printf "%.1f", $2 / 1048576 }' /proc/meminfo)
say "System"
say "  OS:       ${PRETTY_NAME:-unknown} ($(uname -m))"
say "  CPU:      ${CPU:-unknown} - $CORES cores / $THREADS threads"
say "  RAM:      $RAM GB"
if command -v lspci >/dev/null; then
    lspci | grep -Ei 'vga|3d|display' | sed 's/^[^ ]* [^:]*: /  GPU:      /' | tee -a "$REPORT"
fi
if command -v nvidia-smi >/dev/null; then
    say "  NVIDIA:   $(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null | head -1) (driver)"
fi
[ -e "$VAAPI" ] && say "  VAAPI:    $VAAPI present"

if [ "${ID:-}" = ubuntu ] && awk "BEGIN { exit !(${VERSION_ID:-0} < 24.04) }"; then
    NOTES+=("BAMS supports Ubuntu 24.04 or newer; this is ${VERSION_ID}.")
fi
if command -v python3 >/dev/null; then
    PY=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    say "  Python:   $PY"
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
        || NOTES+=("BAMS needs Python 3.11 or newer; this has $PY.")
fi
say ""

# ---- Video conversion -----------------------------------------------------------------------
FF="${BAMS_FFMPEG:-$(command -v ffmpeg || true)}"
BEST1080=""; BEST4K=""; CPU1080=""; AUTO=""
LABEL4K="4K HEVC 10-bit -> 1080p H.264"

works() {  # the same tiny test encode BAMS runs at start-up
    local enc=$1 pre=() vf=format=yuv420p
    if [ "$enc" = h264_vaapi ]; then pre=(-vaapi_device "$VAAPI"); vf=format=nv12,hwupload; fi
    timeout 20 "$FF" -hide_banner -loglevel error -nostdin "${pre[@]}" \
        -f lavfi -i color=black:size=256x256:rate=25:duration=0.2 \
        -vf "$vf" -frames:v 2 -c:v "$enc" -f null - >/dev/null 2>&1
}

enc_args() {  # BAMS's settings for each encoder (stream._encoder_args), 1080p peak 8 Mbit/s
    local cap=(-maxrate 8000k -bufsize 16000k) target=(-b:v 4800k)
    case $1 in
        h264_nvenc) EA=(-c:v h264_nvenc -preset p4 -rc vbr -cq 23 -b:v 0 "${cap[@]}" -profile:v high -no-scenecut 1) ;;
        h264_qsv)   EA=(-c:v h264_qsv -preset veryfast "${target[@]}" "${cap[@]}" -profile:v high) ;;
        h264_amf)   EA=(-c:v h264_amf -usage transcoding -quality speed -rc vbr_peak "${target[@]}" "${cap[@]}" -profile:v high) ;;
        h264_vaapi) EA=(-c:v h264_vaapi "${target[@]}" "${cap[@]}" -profile:v high) ;;
        libx264)    EA=(-c:v libx264 -preset veryfast -crf 22 "${cap[@]}" -profile:v high -sc_threshold 0) ;;
    esac
}

# bench ENCODER CLIP SECONDS SCALE -> prints the speed (x real time); fails if the encoder can't do it
bench() {
    local enc=$1 src=$2 dur=$3 scale=$4 pre=() hw=() vf t0 t1
    enc_args "$enc"
    vf="${scale}format=yuv420p"
    case $enc in
        h264_nvenc) hw=(-hwaccel cuda) ;;
        h264_qsv)   hw=(-hwaccel vaapi) ;;
        h264_vaapi) pre=(-vaapi_device "$VAAPI"); hw=(-hwaccel vaapi -hwaccel_device "$VAAPI")
                    vf="${scale}format=nv12,hwupload" ;;
    esac
    run() { timeout 900 "$FF" -hide_banner -loglevel error -nostdin "${pre[@]}" "$@" -i "$src" \
                -vf "$vf" "${EA[@]}" -an -f null - >/dev/null 2>&1; }
    t0=$(now)
    if ! run "${hw[@]}"; then           # GPU decoding failed: BAMS falls back to the CPU decoder too
        [ ${#hw[@]} -eq 0 ] && return 1
        t0=$(now)
        run || return 1
    fi
    t1=$(now)
    calc "$dur / ($t1 - $t0)"
}

say "Video conversion (what BAMS does when a browser or TV can't play a file as it is)"
if [ -z "$FF" ]; then
    say "  FFmpeg not found: install it (sudo apt install ffmpeg) and run this again. Conversion tests skipped."
    NOTES+=("Conversion not tested (no FFmpeg).")
else
    say "  FFmpeg:   $FF ($("$FF" -version | head -1 | awk '{print $3}'))"
    ENCS=()
    for e in h264_nvenc h264_qsv h264_amf h264_vaapi libx264; do works "$e" && ENCS+=("$e"); done
    AUTO="${ENCS[0]:-none}"
    say "  Working:  ${ENCS[*]:-none}  (BAMS would pick $AUTO automatically)"
    say "  Making test clips..."
    "$FF" -hide_banner -loglevel error -nostdin -f lavfi -i testsrc2=size=1920x1080:rate=24:duration=20 \
        -vf noise=alls=12:allf=t+u -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$TMP/1080p.mkv"
    if "$FF" -hide_banner -encoders 2>/dev/null | grep -q libx265; then
        "$FF" -hide_banner -loglevel error -nostdin -f lavfi -i testsrc2=size=3840x2160:rate=24:duration=10 \
            -vf noise=alls=12:allf=t+u,format=yuv420p10le -c:v libx265 -preset ultrafast -crf 22 \
            -x265-params log-level=error "$TMP/4k.mkv"
    else
        LABEL4K="4K H.264 -> 1080p H.264"
        "$FF" -hide_banner -loglevel error -nostdin -f lavfi -i testsrc2=size=3840x2160:rate=24:duration=10 \
            -vf noise=alls=12:allf=t+u -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$TMP/4k.mkv"
    fi
    say "  Speed in x real time (2.0x = two films converting at once):"
    say "                 1080p H.264 -> 1080p   $LABEL4K"
    for e in "${ENCS[@]}"; do
        s1=$(bench "$e" "$TMP/1080p.mkv" 20 "") || s1=""
        s4=$(bench "$e" "$TMP/4k.mkv" 10 "scale=-2:1080,") || s4=""
        say "$(printf '  %-14s %-24s %s' "$e" "${s1:+${s1}x}${s1:-failed}" "${s4:+${s4}x}${s4:-failed}")"
        if [ -n "$s1" ] && { [ -z "$BEST1080" ] || awk "BEGIN { exit !($s1 > $BEST1080) }"; }; then BEST1080=$s1; fi
        if [ -n "$s4" ] && { [ -z "$BEST4K" ] || awk "BEGIN { exit !($s4 > $BEST4K) }"; }; then BEST4K=$s4; fi
        [ "$e" = libx264 ] && CPU1080=$s1
    done
fi
say ""

# ---- Media drive ----------------------------------------------------------------------------
DISK=""
say "Media drive (every film is read from here, whether it's converted or not)"
if [ -z "$MEDIA" ]; then
    say "  Skipped: pass your media folder to test it (bash bams-hwcheck.sh /path/to/media)."
else
    if [ -f "$MEDIA" ]; then F="$MEDIA"; else
        F=$(find "$MEDIA" -maxdepth 6 -type f \( -iname '*.mkv' -o -iname '*.mp4' -o -iname '*.m2ts' \
              -o -iname '*.ts' -o -iname '*.avi' -o -iname '*.mov' -o -iname '*.m4v' \) \
              -printf '%s\t%p\n' 2>/dev/null | sort -n | tail -1 | cut -f2-)
    fi
    if [ -z "${F:-}" ] || [ ! -r "$F" ]; then
        say "  No readable video file found under $MEDIA."
    else
        SIZE=$(stat -c %s "$F")
        N=$(( SIZE < 2147483648 ? SIZE : 2147483648 ))
        BLOCKS=$(( (N + 4194303) / 4194304 ))
        FS=$(df -T "$F" | awk 'NR == 2 { print $2 }')
        say "  File:     $F ($(calc "$SIZE / 1073741824") GB, $FS)"
        CACHED=""
        t0=$(now)
        if ! dd if="$F" of=/dev/null bs=4M count="$BLOCKS" iflag=direct status=none 2>/dev/null; then
            CACHED=" (read through the cache: may be too high if the file was read recently)"
            t0=$(now)
            dd if="$F" of=/dev/null bs=4M count="$BLOCKS" status=none
        fi
        t1=$(now)
        DISK=$(calc "$N / 1048576 / ($t1 - $t0)")
        say "  Read:     $DISK MB/s over $(calc "$N / 1048576") MB$CACHED"
        [ "$N" -lt 524288000 ] && NOTES+=("The media test file is small; pick a bigger one for a fairer disk number.")
    fi
fi
say ""

# ---- Network --------------------------------------------------------------------------------
LINK=""
say "Network (local link speed; your internet upload limits viewing away from home - check it with a speed test)"
for d in /sys/class/net/*; do
    i=$(basename "$d")
    case $i in lo|docker*|veth*|br-*|virbr*|tun*|tap*|wg*|zt*|tailscale*) continue ;; esac
    [ "$(cat "$d/operstate" 2>/dev/null)" = up ] || continue
    if [ -d "$d/wireless" ]; then
        sp=$(iw dev "$i" link 2>/dev/null | awk '/tx bitrate/ { print int($3) }')
        kind="Wi-Fi"
    else
        sp=$(cat "$d/speed" 2>/dev/null); kind="wired"
    fi
    [ -n "$sp" ] && [ "$sp" -gt 0 ] 2>/dev/null || { say "  $i ($kind): up, speed unknown"; continue; }
    say "  $i ($kind): $sp Mbit/s"
    if [ -z "$LINK" ] || [ "$sp" -gt "$LINK" ]; then LINK=$sp; fi
done
[ -z "$LINK" ] && say "  No connected network link with a known speed."
say ""

# ---- Score (same formula in bams-hwcheck.ps1) -----------------------------------------------
# Full marks: 4 simultaneous 4K->1080p conversions (25), 8 at 1080p (15), CPU x264 at 3x real
# time (15; HDR tone-mapping, subtitle burn-in and the no-GPU fallback run on the CPU),
# 200 MB/s from the media drive (20), a 1 Gbit/s link (15), 8 GB of RAM (10).
TOTAL=0; MAX=0
add() { TOTAL=$(calc "$TOTAL + $(pts "$1" "$2" "$3")"); MAX=$((MAX + $3)); }
[ -n "$BEST4K" ]   && add "$BEST4K" 4 25
[ -n "$BEST1080" ] && add "$BEST1080" 8 15
[ -n "$CPU1080" ]  && add "$CPU1080" 3 15
[ -n "$DISK" ]     && add "$DISK" 200 20
[ -n "$LINK" ]     && add "$LINK" 1000 15
add "$RAM" 8 10
SCORE=$(calc "$TOTAL * 100 / $MAX")

say "What this machine could do for BAMS (rough estimates)"
[ -n "$BEST4K" ]   && say "  4K films converted at once:    about $(floor "$BEST4K")"
[ -n "$BEST1080" ] && say "  1080p films converted at once: about $(floor "$BEST1080")"
[ -n "$DISK" ]     && say "  4K films played as-is at once, by the drive:   about $(floor "$DISK * 8 / 80")"
[ -n "$LINK" ]     && say "  4K films played as-is at once, by the network: about $(floor "$LINK * 0.7 / 80")"
say "  (BAMS limits conversions to 4 at once with a GPU, 2 on the CPU, unless you change it in Settings -> Playback.)"
for n in "${NOTES[@]}"; do say "  Note: $n"; done
say ""
say "SCORE: $SCORE / 100   (out of the $MAX points this run could test)"
say "Summary: host=$(hostname) os=linux conv4k=${BEST4K:-na} conv1080=${BEST1080:-na} cpu1080=${CPU1080:-na} disk=${DISK:-na}MB/s link=${LINK:-na}Mbit/s ram=${RAM}GB auto=${AUTO:-na} score=$SCORE"
say ""
say "Saved to $REPORT"

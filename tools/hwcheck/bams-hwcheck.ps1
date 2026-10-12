# BAMS hardware check for Windows 10 (1809+) / 11, 64-bit.
#
# Measures what BAMS leans on when it serves video: converting video (GPU or CPU), reading
# the media drive, the network link and memory. Run it on each machine you're considering
# (bams-hwcheck.sh on Linux runs the same tests and scores them the same way) and compare.
#
#   powershell -ExecutionPolicy Bypass -File .\bams-hwcheck.ps1 -Media "D:\Media"
#
# It only reads your media. Test clips go in a temporary folder that's deleted at the end.
# The conversion tests need FFmpeg: the BAMS installer's copy is used if BAMS is installed,
# otherwise one on the PATH (or pass -FFmpeg C:\path\to\ffmpeg.exe). Takes about 1-5 minutes.
param(
    [string]$Media = "",
    [string]$FFmpeg = ""
)

$inv = [Globalization.CultureInfo]::InvariantCulture
function F1($x) { [string]::Format($inv, "{0:0.0}", [double]$x) }
function Floor($x) { [string][math]::Floor([double]$x) }
function Pts($v, $full, $weight) { [math]::Min(1.0, [math]::Max(0.0, [double]$v / $full)) * $weight }

$Report = Join-Path $HOME "bams-hwcheck-$env:COMPUTERNAME.txt"
Set-Content -Path $Report -Value $null -Encoding UTF8
function Say([string]$s = "") { Write-Host $s; Add-Content -Path $Report -Value $s -Encoding UTF8 }
$Notes = New-Object System.Collections.Generic.List[string]

$Tmp = Join-Path ([IO.Path]::GetTempPath()) ("bams-hwcheck-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $Tmp | Out-Null

try {
Say "BAMS hardware check - $env:COMPUTERNAME - $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
Say

# ---- System ---------------------------------------------------------------------------------
$os = Get-CimInstance Win32_OperatingSystem
$cpus = @(Get-CimInstance Win32_Processor)
$cores = ($cpus | Measure-Object NumberOfCores -Sum).Sum
$threads = ($cpus | Measure-Object NumberOfLogicalProcessors -Sum).Sum
$Ram = [double](Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB
Say "System"
Say "  OS:       $($os.Caption) $($os.Version) ($($os.OSArchitecture))"
Say "  CPU:      $($cpus[0].Name.Trim()) - $cores cores / $threads threads"
Say "  RAM:      $(F1 $Ram) GB"
foreach ($g in Get-CimInstance Win32_VideoController) { Say "  GPU:      $($g.Name) (driver $($g.DriverVersion))" }
if (-not [Environment]::Is64BitOperatingSystem) { $Notes.Add("BAMS needs 64-bit Windows.") }
if ([int]$os.BuildNumber -lt 17763) { $Notes.Add("BAMS needs Windows 10 1809 or newer.") }
Say

# ---- Video conversion -----------------------------------------------------------------------
if (-not $FFmpeg) {
    $FFmpeg = $env:BAMS_FFMPEG
    if (-not $FFmpeg -and (Test-Path "$env:ProgramFiles\BAMS\ffmpeg\bin\ffmpeg.exe")) { $FFmpeg = "$env:ProgramFiles\BAMS\ffmpeg\bin\ffmpeg.exe" }
    if (-not $FFmpeg) { $c = Get-Command ffmpeg -ErrorAction SilentlyContinue; if ($c) { $FFmpeg = $c.Source } }
}
$Best1080 = $null; $Best4K = $null; $Cpu1080 = $null; $Auto = $null
$Label4K = "4K HEVC 10-bit -> 1080p H.264"

function Run-FF([string[]]$a, [int]$timeoutSec = 900) {
    $p = Start-Process -FilePath $FFmpeg -ArgumentList (($a | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' ') `
        -NoNewWindow -PassThru -RedirectStandardError (Join-Path $Tmp "ff.err") -RedirectStandardOutput (Join-Path $Tmp "ff.out")
    $null = $p.Handle  # without this, Windows PowerShell can lose the exit code
    if (-not $p.WaitForExit($timeoutSec * 1000)) { try { $p.Kill() } catch {}; return $false }
    return $p.ExitCode -eq 0
}

function Works([string]$enc) {  # the same tiny test encode BAMS runs at start-up
    Run-FF @("-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "color=black:size=256x256:rate=25:duration=0.2",
             "-vf", "format=yuv420p", "-frames:v", "2", "-c:v", $enc, "-f", "null", "-") 20
}

function Enc-Args([string]$enc) {  # BAMS's settings for each encoder (stream._encoder_args), 1080p peak 8 Mbit/s
    $cap = @("-maxrate", "8000k", "-bufsize", "16000k"); $target = @("-b:v", "4800k")
    switch ($enc) {
        "h264_nvenc" { @("-c:v", $enc, "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0") + $cap + @("-profile:v", "high", "-no-scenecut", "1") }
        "h264_qsv"   { @("-c:v", $enc, "-preset", "veryfast") + $target + $cap + @("-profile:v", "high") }
        "h264_amf"   { @("-c:v", $enc, "-usage", "transcoding", "-quality", "speed", "-rc", "vbr_peak") + $target + $cap + @("-profile:v", "high") }
        "libx264"    { @("-c:v", $enc, "-preset", "veryfast", "-crf", "22") + $cap + @("-profile:v", "high", "-sc_threshold", "0") }
    }
}

# Speed in x real time, or $null if the encoder can't do it
function Bench([string]$enc, [string]$src, [double]$dur, [string]$scale) {
    $hw = @(switch ($enc) { "h264_nvenc" { "-hwaccel", "cuda" } { $_ -in "h264_qsv", "h264_amf" } { "-hwaccel", "d3d11va" } })
    $tail = @("-i", $src, "-vf", "${scale}format=yuv420p") + (Enc-Args $enc) + @("-an", "-f", "null", "-")
    $head = @("-hide_banner", "-loglevel", "error", "-nostdin")
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $ok = Run-FF ($head + $hw + $tail)
    if (-not $ok -and $hw.Count -gt 0) {  # GPU decoding failed: BAMS falls back to the CPU decoder too
        $sw.Restart()
        $ok = Run-FF ($head + $tail)
    }
    if (-not $ok) { return $null }
    return $dur / $sw.Elapsed.TotalSeconds
}

Say "Video conversion (what BAMS does when a browser or TV can't play a file as it is)"
if (-not $FFmpeg -or -not (Test-Path $FFmpeg)) {
    Say "  FFmpeg not found: install BAMS (its installer fetches FFmpeg) or pass -FFmpeg C:\path\to\ffmpeg.exe. Conversion tests skipped."
    $Notes.Add("Conversion not tested (no FFmpeg).")
} else {
    $ver = ((& $FFmpeg -version | Select-Object -First 1) -split ' ')[2]
    Say "  FFmpeg:   $FFmpeg ($ver)"
    $encs = @("h264_nvenc", "h264_qsv", "h264_amf", "libx264") | Where-Object { Works $_ }
    $Auto = if ($encs) { @($encs)[0] } else { "none" }
    Say "  Working:  $(if ($encs) { $encs -join ' ' } else { 'none' })  (BAMS would pick $Auto automatically)"
    Say "  Making test clips..."
    $c1080 = Join-Path $Tmp "1080p.mkv"; $c4k = Join-Path $Tmp "4k.mkv"
    Run-FF @("-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=24:duration=20",
             "-vf", "noise=alls=12:allf=t+u", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", $c1080) | Out-Null
    $has265 = (& $FFmpeg -hide_banner -encoders 2>$null | Select-String "libx265") -ne $null
    if ($has265) {
        Run-FF @("-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc2=size=3840x2160:rate=24:duration=10",
                 "-vf", "noise=alls=12:allf=t+u,format=yuv420p10le", "-c:v", "libx265", "-preset", "ultrafast", "-crf", "22",
                 "-x265-params", "log-level=error", $c4k) | Out-Null
    } else {
        $Label4K = "4K H.264 -> 1080p H.264"
        Run-FF @("-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc2=size=3840x2160:rate=24:duration=10",
                 "-vf", "noise=alls=12:allf=t+u", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", $c4k) | Out-Null
    }
    Say "  Speed in x real time (2.0x = two films converting at once):"
    Say "                 1080p H.264 -> 1080p   $Label4K"
    foreach ($e in $encs) {
        $s1 = Bench $e $c1080 20 ""
        $s4 = Bench $e $c4k 10 "scale=-2:1080,"
        $t1 = if ($null -ne $s1) { (F1 $s1) + "x" } else { "failed" }
        $t4 = if ($null -ne $s4) { (F1 $s4) + "x" } else { "failed" }
        Say ("  {0,-14} {1,-24} {2}" -f $e, $t1, $t4)
        if ($null -ne $s1 -and ($null -eq $Best1080 -or $s1 -gt $Best1080)) { $Best1080 = $s1 }
        if ($null -ne $s4 -and ($null -eq $Best4K -or $s4 -gt $Best4K)) { $Best4K = $s4 }
        if ($e -eq "libx264") { $Cpu1080 = $s1 }
    }
}
Say

# ---- Media drive ----------------------------------------------------------------------------
$Disk = $null
Say "Media drive (every film is read from here, whether it's converted or not)"
if (-not $Media) {
    Say "  Skipped: pass your media folder to test it (-Media `"D:\Media`")."
} else {
    $file = if (Test-Path -LiteralPath $Media -PathType Leaf) { Get-Item -LiteralPath $Media } else {
        Get-ChildItem -LiteralPath $Media -Recurse -Depth 6 -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in ".mkv", ".mp4", ".m2ts", ".ts", ".avi", ".mov", ".m4v" } |
            Sort-Object Length -Descending | Select-Object -First 1
    }
    if (-not $file) {
        Say "  No readable video file found under $Media."
    } else {
        $n = [math]::Min([int64]$file.Length, [int64]2GB)
        $drive = if ($file.FullName -like "\\*") { "network share" } else {
            $v = Get-Volume -FilePath $file.FullName -ErrorAction SilentlyContinue
            if ($v) { "$($v.FileSystemType), $($v.DriveType)" } else { "local" }
        }
        Say "  File:     $($file.FullName) ($(F1 ($file.Length / 1GB)) GB, $drive)"
        $buf = New-Object byte[] (4MB)
        $cached = ""
        function Read-File($opts) {
            $fs = New-Object IO.FileStream($file.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite, 4096, $opts)
            try {
                $sw = [Diagnostics.Stopwatch]::StartNew(); $got = 0
                while ($got -lt $n) { $r = $fs.Read($buf, 0, $buf.Length); if ($r -le 0) { break }; $got += $r }
                return @($got, $sw.Elapsed.TotalSeconds)
            } finally { $fs.Dispose() }
        }
        try {
            $res = Read-File ([IO.FileOptions]0x20000000)  # FILE_FLAG_NO_BUFFERING: read the drive, not the cache
        } catch {
            $cached = " (read through the cache: may be too high if the file was read recently)"
            $res = Read-File ([IO.FileOptions]::SequentialScan)
        }
        $Disk = $res[0] / 1MB / $res[1]
        Say "  Read:     $(F1 $Disk) MB/s over $(F1 ($res[0] / 1MB)) MB$cached"
        if ($n -lt 500MB) { $Notes.Add("The media test file is small; pick a bigger one for a fairer disk number.") }
    }
}
Say

# ---- Network --------------------------------------------------------------------------------
$Link = $null
Say "Network (local link speed; your internet upload limits viewing away from home - check it with a speed test)"
foreach ($a in Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object Status -eq "Up") {
    $sp = [math]::Round([double]$a.Speed / 1e6)
    $kind = if ($a.PhysicalMediaType -match "802\.11|Wireless") { "Wi-Fi" } else { "wired" }
    Say "  $($a.Name) ($kind): $sp Mbit/s"
    if ($sp -gt 0 -and ($null -eq $Link -or $sp -gt $Link)) { $Link = $sp }
}
if ($null -eq $Link) { Say "  No connected network link with a known speed." }
Say

# ---- Score (same formula in bams-hwcheck.sh) ------------------------------------------------
# Full marks: 4 simultaneous 4K->1080p conversions (25), 8 at 1080p (15), CPU x264 at 3x real
# time (15; HDR tone-mapping, subtitle burn-in and the no-GPU fallback run on the CPU),
# 200 MB/s from the media drive (20), a 1 Gbit/s link (15), 8 GB of RAM (10).
$total = 0.0; $max = 0
function Add-Pts($v, $full, $w) { $script:total += Pts $v $full $w; $script:max += $w }
if ($null -ne $Best4K)   { Add-Pts $Best4K 4 25 }
if ($null -ne $Best1080) { Add-Pts $Best1080 8 15 }
if ($null -ne $Cpu1080)  { Add-Pts $Cpu1080 3 15 }
if ($null -ne $Disk)     { Add-Pts $Disk 200 20 }
if ($null -ne $Link)     { Add-Pts $Link 1000 15 }
Add-Pts $Ram 8 10
$Score = $total * 100 / $max

Say "What this machine could do for BAMS (rough estimates)"
if ($null -ne $Best4K)   { Say "  4K films converted at once:    about $(Floor $Best4K)" }
if ($null -ne $Best1080) { Say "  1080p films converted at once: about $(Floor $Best1080)" }
if ($null -ne $Disk)     { Say "  4K films played as-is at once, by the drive:   about $(Floor ($Disk * 8 / 80))" }
if ($null -ne $Link)     { Say "  4K films played as-is at once, by the network: about $(Floor ($Link * 0.7 / 80))" }
Say "  (BAMS limits conversions to 4 at once with a GPU, 2 on the CPU, unless you change it in Settings -> Playback.)"
foreach ($m in $Notes) { Say "  Note: $m" }
Say
Say "SCORE: $(F1 $Score) / 100   (out of the $max points this run could test)"
$na = { param($v, $unit) if ($null -ne $v) { (F1 $v) + $unit } else { "na" } }
Say ("Summary: host=$env:COMPUTERNAME os=windows conv4k=$(& $na $Best4K '') conv1080=$(& $na $Best1080 '') cpu1080=$(& $na $Cpu1080 '') " +
     "disk=$(& $na $Disk 'MB/s') link=$(& $na $Link 'Mbit/s') ram=$(F1 $Ram)GB auto=$Auto score=$(F1 $Score)")
Say
Say "Saved to $Report"
} finally {
    Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

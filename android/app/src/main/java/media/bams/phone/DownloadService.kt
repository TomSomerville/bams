package media.bams.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.io.IOException

/**
 * Fetches queued downloads one file at a time, as the original files (`/api/files/{id}/download`), resuming a cut
 * one where it stopped (HTTP Range on a `.part` file). Runs as a foreground service with a progress notification so
 * it carries on with the screen off. When the server can't be reached it stops; queued files go on the next time
 * the app opens or reaches the server (MainActivity calls [start]).
 */
class DownloadService : Service() {
    private val app get() = application as App
    @Volatile private var worker: Thread? = null
    private var wake: PowerManager.WakeLock? = null
    private var wifi: WifiManager.WifiLock? = null
    private var lastNote = 0L
    private var lastEmit = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val n = note("Getting downloads ready", null, 0, 0)
        if (Build.VERSION.SDK_INT >= 29) startForeground(NOTE, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else startForeground(NOTE, n)
        if (worker?.isAlive != true) {
            worker = Thread({ run() }, "downloads").also { it.start() }
        }
        return START_NOT_STICKY
    }

    // Android 15 limits data transfers in the background to 6 hours a day: stop; the rest goes on next time
    override fun onTimeout(startId: Int, fgsType: Int) {
        worker?.interrupt()
        stopSelf()
    }

    override fun onDestroy() {
        worker?.interrupt()
        release()
        super.onDestroy()
    }

    private fun run() {
        val pm = getSystemService(PowerManager::class.java)
        wake = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "bams:downloads").apply { acquire(6 * 3600_000L) }
        @Suppress("DEPRECATION")
        wifi = (applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager)
            .createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "bams:downloads").apply { acquire() }
        val store = app.store
        val unreachable = mutableSetOf<String>()  // servers that didn't answer this time
        var waited = 0
        try {
            while (!Thread.currentThread().isInterrupted) {
                fetchImages(unreachable)
                val f = nextReachable(unreachable) ?: break
                if (store.wifiOnly && metered()) {
                    // half an hour without Wi-Fi: stop; they go on the next time the app opens
                    if (++waited > 180) break
                    store.waiting = "wifi"
                    app.emit("downloads")
                    notify(note("Waiting for Wi-Fi", "Downloads go on over Wi-Fi (Settings → This phone)", 0, 0))
                    Thread.sleep(10_000)
                    continue
                }
                waited = 0
                if (store.waiting != null) { store.waiting = null; app.emit("downloads") }
                val base = app.servers.reach(f.sid)
                if (base == null) {
                    unreachable += f.sid
                    continue
                }
                fetch(f, base)
            }
        } catch (e: InterruptedException) {
            // stopped (Android's time limit, or the app went away)
        } finally {
            store.waiting = null
            store.save()
            app.emit("downloads")
            release()
            app.onMain { stopForeground(STOP_FOREGROUND_REMOVE); stopSelf() }
        }
    }

    /** The next queued file, in the order downloads were asked for, of a server that hasn't failed to answer. */
    private fun nextReachable(skip: Set<String>): Store.FileEntry? {
        val store = app.store
        return synchronized(store) {
            store.allRoots().flatMap { r -> (store.manifest(r.key)?.optJSONArray("files")?.let { a ->
                List(a.length()) { store.file("${r.sid}|${a.getJSONObject(it).getInt("id")}") } } ?: emptyList()) }
                .filterNotNull().firstOrNull { it.state == "queued" && it.sid !in skip }
        }
    }

    private fun metered(): Boolean {
        val cm = getSystemService(ConnectivityManager::class.java)
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return true
        return !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
    }

    /** The pictures of each download (posters, stills, album art): small, fetched before the files. */
    private fun fetchImages(skip: MutableSet<String>) {
        val store = app.store
        for (r in store.allRoots()) {
            if (r.sid in skip) continue
            val imgs = store.manifest(r.key)?.optJSONArray("images") ?: continue
            val missing = List(imgs.length()) { imgs.getString(it) }.filter { !store.image(r.sid, it).exists() && it !in failedImages }
            if (missing.isEmpty()) continue
            val base = app.servers.reach(r.sid) ?: run { skip += r.sid; null } ?: continue
            val token = app.servers.get(r.sid)?.token
            for (url in missing) {
                if (Thread.currentThread().isInterrupted) return
                try {
                    val out = store.image(r.sid, url).apply { parentFile?.mkdirs() }
                    val c = Http.open(base + url, token)
                    try {
                        if (c.responseCode != 200) { failedImages += url; continue }
                        val tmp = File(out.path + ".part")
                        c.inputStream.use { i -> FileOutputStream(tmp).use { o -> i.copyTo(o) } }
                        tmp.renameTo(out)
                    } finally {
                        c.disconnect()
                    }
                } catch (e: IOException) {
                    failedImages += url
                }
            }
            app.emit("downloads")
        }
    }

    private fun fetch(f: Store.FileEntry, base: String) {
        val store = app.store
        val token = app.servers.get(f.sid)?.token
        val dir = store.dir(f)
        if (dir == null) {
            fail(f, "The storage it goes to isn't there (an SD card taken out?).")
            return
        }
        dir.mkdirs()
        val part = File(dir, f.name + ".part")
        val title = store.rootsOf(f).firstOrNull()?.title ?: f.name
        f.state = "downloading"
        f.error = null
        app.emit("downloads")
        var tries = 0
        while (true) {
            try {
                download(f, base + f.url, token, part, title)
                break
            } catch (e: HttpError) {
                fail(f, e.message ?: "The server refused it.")
                return
            } catch (e: IOException) {
                if (f.state == "removed") return
                if (++tries >= 4) {
                    // offline now: leave it queued for later rather than calling it failed
                    if (app.servers.reach(f.sid, fresh = true) == null) { f.state = "queued"; store.save(); return }
                    fail(f, "The connection kept breaking off: ${e.message}")
                    return
                }
                Log.w(App.TAG, "download of ${f.name} broke off (${e.message}), trying again")
                Thread.sleep(5_000L * tries)
            }
        }
        if (f.state == "removed") { part.delete(); return }
        val target = File(dir, f.name)
        target.delete()
        if (!part.renameTo(target)) { fail(f, "Couldn't save it on the phone."); return }
        // its subtitles (text tracks as WebVTT), for playing offline
        for (i in 0 until f.subs.length()) {
            val s = f.subs.getJSONObject(i)
            val url = s.str("url") ?: continue
            try {
                val out = File(File(dir, "subs"), Store.safeName(s.getString("id")) + ".vtt").apply { parentFile?.mkdirs() }
                val c = Http.open(base + url, token)
                try {
                    if (c.responseCode == 200) c.inputStream.use { i -> FileOutputStream(out).use { o -> i.copyTo(o) } }
                } finally {
                    c.disconnect()
                }
            } catch (e: IOException) { /* plays without that one */ }
        }
        f.got = f.size
        f.state = "done"
        store.save()
        app.emit("downloads")
    }

    private fun download(f: Store.FileEntry, url: String, token: String?, part: File, title: String) {
        val have = if (part.exists()) part.length() else 0L
        if (f.size in 1..have) { f.got = have; return }  // all here already
        val c = Http.open(url, token, timeout = 30_000)
        if (have > 0) c.setRequestProperty("Range", "bytes=$have-")
        try {
            val code = c.responseCode
            if (code >= 400) {
                val text = c.errorStream?.use { it.readBytes().decodeToString() } ?: ""
                throw HttpError(code, Http.detail(code, text))
            }
            val append = code == 206
            var got = if (append) have else 0L
            val free = part.parentFile?.usableSpace ?: Long.MAX_VALUE
            if (f.size - got > free) throw HttpError(507, "Not enough space on the phone (${(f.size - got) / 1_000_000} MB needed).")
            c.inputStream.use { input ->
                FileOutputStream(part, append).use { out ->
                    val buf = ByteArray(256 * 1024)
                    while (true) {
                        if (f.state == "removed") return
                        if (Thread.currentThread().isInterrupted) throw InterruptedException()
                        val n = input.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        got += n
                        f.got = got
                        progress(title, f)
                    }
                }
            }
            if (f.size > 0 && got < f.size) throw IOException("the connection closed early")
        } finally {
            c.disconnect()
        }
    }

    private fun progress(title: String, f: Store.FileEntry) {
        val now = System.currentTimeMillis()
        if (now - lastEmit > 1000) {
            lastEmit = now
            app.emit("downloads")
        }
        if (now - lastNote > 1500) {
            lastNote = now
            val left = app.store.pending()
            notify(note("Downloading $title", if (left > 1) "$left files to go" else null, f.got, f.size))
            app.store.save()
        }
    }

    private fun fail(f: Store.FileEntry, why: String) {
        if (f.state == "removed") return
        f.state = "failed"
        f.error = why
        app.store.save()
        app.emit("downloads")
    }

    private fun release() {
        try { wake?.takeIf { it.isHeld }?.release() } catch (e: Exception) {}
        try { wifi?.takeIf { it.isHeld }?.release() } catch (e: Exception) {}
        wake = null
        wifi = null
    }

    private fun notify(n: Notification) {
        getSystemService(NotificationManager::class.java).notify(NOTE, n)
    }

    private fun note(title: String, text: String?, got: Long, size: Long): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Downloads", NotificationManager.IMPORTANCE_LOW))
        }
        val open = PendingIntent.getActivity(this, 0,
            Intent(this, MainActivity::class.java).putExtra(MainActivity.OPEN, "downloads")
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val b = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(title)
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
        if (text != null) b.setContentText(text)
        if (size > 0) b.setProgress(1000, (got * 1000 / size).toInt(), false)
        return b.build()
    }

    companion object {
        private const val CHANNEL = "downloads"
        private const val NOTE = 1
        private val failedImages = mutableSetOf<String>()

        /** Start (or wake) the downloads, when there are any queued. Call only while the app is on screen: Android
         *  doesn't let an app start a foreground service from the background. */
        fun start(context: Context) {
            if (App.instance.store.pending() == 0) return
            try {
                context.startForegroundService(Intent(context, DownloadService::class.java))
            } catch (e: Exception) {
                Log.w(App.TAG, "couldn't start downloads: ${e.message}")
            }
        }
    }
}

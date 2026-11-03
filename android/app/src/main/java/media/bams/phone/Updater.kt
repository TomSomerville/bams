package media.bams.phone

import android.app.AlertDialog
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.util.Log
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.security.MessageDigest

/**
 * The app updates itself from the GitHub releases, as the server does (server/bams/updates.py): the newest release with
 * a BAMS-Android-<v>.apk (not every release has one), checked against the SHA-256 GitHub lists for it, then handed to
 * Android's installer. Android asks the person to allow it and only installs an APK signed with the app's own key.
 * Offered once a day (`offer`); Downloads has a button (phone/pages.tsx AppUpdate). Debug builds never update: their
 * key differs from the releases'.
 */
class Updater(private val activity: MainActivity) {
    private val app = activity.application as App
    private val prefs = activity.getSharedPreferences("updates", Context.MODE_PRIVATE)
    private val debug = activity.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
    /** waiting for the person to allow installs in Android's settings: goes on when they come back (`offer`) */
    private var waiting: Release? = null

    class Release(val version: String, val url: String, val sha256: String, val size: Long) {
        fun json(): JSONObject = JSONObject().put("version", version).put("size", size)
    }

    /** The newest release with an APK, if it's newer than this app. */
    fun check(): Release? {
        if (debug) return null
        val c = Http.open(RELEASES, null)
        val releases = try {
            val code = try { c.responseCode } catch (e: IOException) { throw HttpError(0, "Can't reach GitHub right now.") }
            if (code != 200) throw HttpError(code, "GitHub didn't answer (HTTP $code). Try again later.")
            JSONArray(c.inputStream.use { it.readBytes().decodeToString() })
        } finally {
            c.disconnect()
        }
        var best: Release? = null
        for (i in 0 until releases.length()) {
            val r = releases.getJSONObject(i)
            if (r.optBoolean("draft") || r.optBoolean("prerelease")) continue
            val assets = r.getJSONArray("assets")
            for (k in 0 until assets.length()) {
                val a = assets.getJSONObject(k)
                val version = APK.matchEntire(a.getString("name"))?.groupValues?.get(1) ?: continue
                val sha = a.str("digest")?.removePrefix("sha256:") ?: continue  // nothing to check it against: not offered
                if (best == null || newer(version, best.version)) {
                    best = Release(version, a.getString("browser_download_url"), sha, a.optLong("size"))
                }
            }
        }
        return best?.takeIf { newer(it.version, app.version()) }
    }

    /** Download `r`, check it, and start Android's installer; the first time, Android's settings to allow that. Off
     *  the main thread. */
    fun install(r: Release) {
        if (!activity.packageManager.canRequestPackageInstalls()) {
            waiting = r
            activity.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}")))
            return
        }
        val dir = File(activity.cacheDir, "updates").apply { deleteRecursively(); mkdirs() }
        val apk = File(dir, "BAMS-Android-${r.version}.apk")
        try {
            download(r, apk)
            val installer = activity.packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
                .apply { setAppPackageName(activity.packageName) }
            if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
            val id = installer.createSession(params)
            installer.openSession(id).use { s ->
                s.openWrite("base.apk", 0, apk.length()).use { out ->
                    apk.inputStream().use { it.copyTo(out) }
                    s.fsync(out)
                }
                // Android answers on this intent: onNewIntent -> installerAnswer
                val answer = Intent(activity, MainActivity::class.java).setAction(ANSWER)
                val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
                s.commit(PendingIntent.getActivity(activity, id, answer, flags).intentSender)
            }
        } finally {
            apk.delete()
        }
    }

    private fun download(r: Release, to: File) {
        val c = Http.open(r.url, null, timeout = 60_000)
        try {
            val code = try { c.responseCode } catch (e: IOException) { throw HttpError(0, "Can't reach GitHub right now.") }
            if (code != 200) throw HttpError(code, "The download failed (HTTP $code). Try again later.")
            val hash = MessageDigest.getInstance("SHA-256")
            c.inputStream.use { input ->
                to.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        hash.update(buf, 0, n)
                        out.write(buf, 0, n)
                    }
                }
            }
            if (hash.digest().joinToString("") { "%02x".format(it) } != r.sha256) throw IOException("The download was damaged. Try again.")
        } finally {
            c.disconnect()
        }
    }

    /** What Android says about an install: it may need the person's OK first. */
    @Suppress("DEPRECATION")
    fun installerAnswer(intent: Intent) {
        if (intent.action != ANSWER) return
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION ->
                intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)?.let { activity.startActivity(it) }
            PackageInstaller.STATUS_SUCCESS -> {}
            PackageInstaller.STATUS_FAILURE_ABORTED -> {}  // they said no
            else -> {
                Log.w(App.TAG, "update: ${intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)}")
                toast("The update couldn't be installed.")
            }
        }
    }

    /** At most once a day: if there's a newer version, ask. A failed check says nothing. */
    fun offer() {
        waiting?.let { r ->
            waiting = null
            if (activity.packageManager.canRequestPackageInstalls()) start(r)
            return
        }
        val now = System.currentTimeMillis()
        if (debug || now - prefs.getLong("checked", 0) < DAY) return
        prefs.edit().putLong("checked", now).apply()
        Thread {
            val r = try { check() } catch (e: Exception) { Log.i(App.TAG, "update check: ${e.message}"); null }
            if (r != null) app.onMain { ask(r) }
        }.start()
    }

    private fun ask(r: Release) {
        if (activity.isFinishing || activity.isDestroyed) return
        AlertDialog.Builder(activity)
            .setTitle("BAMS for Android ${r.version}")
            .setMessage("A new version of the app is ready. Music stops and the app closes while it installs.")
            .setPositiveButton("Update") { _, _ -> start(r) }
            .setNegativeButton("Later", null)
            .show()
    }

    private fun start(r: Release) {
        toast("Downloading the update…")
        Thread {
            try {
                install(r)
            } catch (e: Exception) {
                Log.w(App.TAG, "update: ${e.message}")
                app.onMain { toast(e.message ?: "The update failed.") }
            }
        }.start()
    }

    private fun toast(text: String) = Toast.makeText(activity, text, Toast.LENGTH_LONG).show()

    companion object {
        private const val RELEASES = "https://api.github.com/repos/TomSomerville/bams/releases?per_page=50"
        private const val DAY = 24 * 3600 * 1000L
        private const val ANSWER = "media.bams.phone.UPDATE_ANSWER"
        private val APK = Regex("""BAMS-Android-(\d+(?:\.\d+)*)\.apk""")

        /** "0.2.10" is newer than "0.2.9". */
        fun newer(a: String, than: String): Boolean {
            val x = a.split(".").map { it.toIntOrNull() ?: 0 }
            val y = than.split(".").map { it.toIntOrNull() ?: 0 }
            for (i in 0 until maxOf(x.size, y.size)) {
                val d = x.getOrElse(i) { 0 } - y.getOrElse(i) { 0 }
                if (d != 0) return d > 0
            }
            return false
        }
    }
}

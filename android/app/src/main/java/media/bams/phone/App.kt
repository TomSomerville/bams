package media.bams.phone

import android.app.Application
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors

/**
 * The app's long-lived parts: the server list, the downloads catalog, the progress made offline, and a way to tell
 * the page (MainActivity's bridge) that something changed. Downloads and music run in services; both use these.
 */
class App : Application() {
    lateinit var servers: Servers
        private set
    lateinit var store: Store
        private set
    lateinit var progress: Progress
        private set

    /** page events: (name, data) */
    val listeners = CopyOnWriteArrayList<(String, Any?) -> Unit>()
    private val main = Handler(Looper.getMainLooper())

    /** background work that touches the network or the disk, one task at a time (keeps the catalog consistent) */
    val io = Executors.newSingleThreadExecutor()

    override fun onCreate() {
        super.onCreate()
        servers = Servers(this)
        store = Store(this)
        progress = Progress(this)
    }

    /** Tell every open page (bridge event `name`), on the main thread. */
    fun emit(name: String, data: Any? = null) {
        main.post { for (l in listeners) l(name, data) }
    }

    fun onMain(f: () -> Unit) {
        main.post(f)
    }

    fun version(): String =
        try { packageManager.getPackageInfo(packageName, 0).versionName } catch (e: Exception) { null } ?: "?"

    companion object {
        const val TAG = "BAMS"
        lateinit var instance: App
            private set
    }

    init {
        instance = this
    }
}

/** A JSONObject's optional string ("null" in JSON is null here, not the text "null"). */
fun JSONObject.str(key: String): String? = if (isNull(key)) null else optString(key)

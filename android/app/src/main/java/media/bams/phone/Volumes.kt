package media.bams.phone

import android.content.Context
import android.os.Environment
import android.os.StatFs
import android.os.storage.StorageManager
import org.json.JSONObject
import java.io.File

/**
 * Where downloads can go: the app's own folder on each storage the phone has (internal storage, an SD card).
 * No permission is needed for these; Android deletes them with the app.
 */
object Volumes {
    data class Volume(val id: String, val label: String, val dir: File, val removable: Boolean) {
        fun json(): JSONObject {
            // the app's folder there (dir's parent) always exists; BAMS/ only after a first download
            val st = try { StatFs((dir.parentFile ?: dir).path) } catch (e: Exception) { null }
            return JSONObject().put("id", id).put("label", label).put("removable", removable)
                .put("free", st?.availableBytes ?: 0L).put("total", st?.totalBytes ?: 0L)
        }
    }

    fun all(context: Context): List<Volume> {
        val sm = context.getSystemService(StorageManager::class.java)
        var sd = 0
        return context.getExternalFilesDirs(null).filterNotNull()
            .filter { Environment.getExternalStorageState(it) == Environment.MEDIA_MOUNTED }
            .map { dir ->
                val v = sm.getStorageVolume(dir)
                val removable = v?.isRemovable ?: false
                // "primary" for the phone's own storage, the SD card's UUID otherwise (stays the same across reboots)
                val id = if (v == null || v.isPrimary) "primary" else (v.uuid ?: dir.path)
                val label = when {
                    v == null || v.isPrimary -> "This phone"
                    else -> v.getDescription(context).ifBlank { if (removable) "SD card ${++sd}" else "Storage" }
                }
                Volume(id, label, File(dir, "BAMS"), removable)
            }
    }

    /** The volume [id], or the phone's own storage when it's gone (an SD card taken out). */
    fun get(context: Context, id: String?): Volume? {
        val vs = all(context)
        return vs.find { it.id == id } ?: vs.firstOrNull()
    }

    fun mounted(context: Context, id: String): Boolean = all(context).any { it.id == id }
}

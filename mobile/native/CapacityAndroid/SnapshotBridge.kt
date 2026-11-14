import android.app.Application
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import dev.onejs.one.source.OneModule

// Hands the latest capacity snapshot to the home-screen widgets; see targets/android-widget.
object SnapshotBridge : OneModule {
    private val widgets = listOf(
        "dev.mako.capacity.widget.CapacitySmallWidget",
        "dev.mako.capacity.widget.CapacityMediumWidget",
    )

    fun publish(json: String): Map<String, String> {
        val context = application() ?: return mapOf("widget" to "no-context", "watch" to "unsupported")
        context.getSharedPreferences("capacity", Context.MODE_PRIVATE).edit().putString("snapshot", json).apply()
        val manager = AppWidgetManager.getInstance(context)
        var placed = 0
        for (name in widgets) {
            val component = ComponentName(context.packageName, name)
            val ids = manager.getAppWidgetIds(component)
            if (ids.isEmpty()) continue
            placed += ids.size
            val intent = Intent(AppWidgetManager.ACTION_APPWIDGET_UPDATE)
                .setComponent(component)
                .putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids)
            context.sendBroadcast(intent)
        }
        return mapOf("widget" to if (placed > 0) "written" else "no-widget", "watch" to "unsupported")
    }

    private fun application(): Application? = runCatching {
        Class.forName("android.app.ActivityThread").getMethod("currentApplication").invoke(null) as? Application
    }.getOrNull()
}

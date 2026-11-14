package dev.mako.capacity.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.PorterDuff
import android.graphics.PorterDuffColorFilter
import android.graphics.RectF
import android.view.View
import android.widget.RemoteViews
import dev.mako.capacity.R
import org.json.JSONObject
import kotlin.math.min

data class WidgetAgent(
    val provider: String,
    val heading: String,
    val step: String,
    val name: String,
    val progress: Double?,
    val ring: Double,
    val state: String,
    val signal: String,
)

object AgentSnapshotStore {
    fun load(context: Context): List<WidgetAgent> {
        val text = context.getSharedPreferences("capacity", Context.MODE_PRIVATE).getString("snapshot", null) ?: return emptyList()
        return runCatching {
            val list = JSONObject(text).optJSONArray("agents") ?: return emptyList()
            (0 until list.length()).map { index ->
                val item = list.getJSONObject(index)
                WidgetAgent(
                    provider = item.optString("provider"),
                    heading = item.optString("heading"),
                    step = item.optString("step"),
                    name = item.optString("name"),
                    progress = if (item.isNull("progress")) null else item.optDouble("progress"),
                    ring = item.optDouble("ring", 0.0),
                    state = item.optString("state"),
                    signal = item.optString("signal", "gray"),
                )
            }
        }.getOrDefault(emptyList())
    }
}

// The agents dock's ring: a circle filled clockwise from the top to the progress, in the status colour.
object AgentRingPainter {
    fun draw(context: Context, agent: WidgetAgent, sizeDp: Int): Bitmap {
        val density = context.resources.displayMetrics.density
        val size = (sizeDp * density).toInt()
        val stroke = 3.5f * density
        val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val inset = stroke / 2
        val rect = RectF(inset, inset, size - inset, size - inset)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = stroke
            strokeCap = Paint.Cap.ROUND
            color = context.getColor(R.color.capacity_track)
        }
        canvas.drawOval(rect, paint)
        if (agent.ring > 0) {
            paint.color = colour(context, agent.signal)
            canvas.drawArc(rect, -90f, (360 * min(agent.ring, 100.0) / 100).toFloat(), false, paint)
        }
        val icon = when (agent.provider) {
            "Claude" -> R.drawable.provider_claude
            "Codex" -> R.drawable.provider_codex
            else -> null
        }
        if (icon != null) {
            val mark = BitmapFactory.decodeResource(context.resources, icon)
            val side = size * 0.43f
            val target = RectF((size - side) / 2, (size - side) / 2, (size + side) / 2, (size + side) / 2)
            val tint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG).apply {
                colorFilter = PorterDuffColorFilter(context.getColor(R.color.capacity_text), PorterDuff.Mode.SRC_IN)
            }
            canvas.drawBitmap(mark, null, target, tint)
        }
        return bitmap
    }

    fun colour(context: Context, signal: String): Int = context.getColor(
        when (signal) {
            "red" -> R.color.capacity_signal_red
            "yellow" -> R.color.capacity_signal_yellow
            "green" -> R.color.capacity_signal_green
            else -> R.color.capacity_secondary
        },
    )
}

class AgentsWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val views = render(context)
        ids.forEach { manager.updateAppWidget(it, views) }
    }

    private fun render(context: Context): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.agents_widget)
        views.removeAllViews(R.id.agents_list)
        val agents = AgentSnapshotStore.load(context).take(3)
        views.setViewVisibility(R.id.agents_empty, if (agents.isEmpty()) View.VISIBLE else View.GONE)
        agents.forEach { views.addView(R.id.agents_list, row(context, it)) }
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
        if (launch != null) {
            val pending = PendingIntent.getActivity(context, 1, launch, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            views.setOnClickPendingIntent(R.id.agents_root, pending)
        }
        return views
    }

    private fun row(context: Context, agent: WidgetAgent): RemoteViews {
        val row = RemoteViews(context.packageName, R.layout.agents_widget_row)
        row.setImageViewBitmap(R.id.agent_ring, AgentRingPainter.draw(context, agent, 30))
        row.setTextViewText(R.id.agent_heading, agent.heading)
        row.setTextViewText(R.id.agent_step, agent.step.ifEmpty { agent.name })
        row.setTextViewText(R.id.agent_progress, agent.progress?.let { "${it.toInt()}%" } ?: agent.state)
        row.setTextColor(R.id.agent_progress, AgentRingPainter.colour(context, agent.signal))
        return row
    }
}

package dev.mako.capacity.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PathMeasure
import android.graphics.PorterDuff
import android.graphics.PorterDuffColorFilter
import android.graphics.RectF
import android.view.View
import android.widget.RemoteViews
import dev.mako.capacity.R
import org.json.JSONObject
import kotlin.math.min

data class WidgetAccount(val provider: String, val used: Double?, val window: String, val resetAt: Double?, val signal: String)

// The app writes this snapshot through native/CapacityAndroid/SnapshotBridge.kt.
object SnapshotStore {
    fun load(context: Context): List<WidgetAccount> {
        val text = context.getSharedPreferences("capacity", Context.MODE_PRIVATE).getString("snapshot", null) ?: return emptyList()
        return runCatching {
            val list = JSONObject(text).getJSONArray("accounts")
            (0 until list.length()).map { index ->
                val item = list.getJSONObject(index)
                WidgetAccount(
                    provider = item.optString("provider"),
                    used = if (item.isNull("used")) null else item.optDouble("used"),
                    window = item.optString("window"),
                    resetAt = if (item.isNull("resetAt")) null else item.optDouble("resetAt"),
                    signal = item.optString("signal", "green"),
                )
            }
        }.getOrDefault(emptyList())
    }
}

// Same geometry as the dock's ring: rounded square, 0.30 corner, 4dp stroke, filled clockwise from the top.
object RingPainter {
    fun draw(context: Context, account: WidgetAccount, sizeDp: Int): Bitmap {
        val density = context.resources.displayMetrics.density
        val size = (sizeDp * density).toInt()
        val stroke = 4f * density
        val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val inset = stroke / 2
        val rect = RectF(inset, inset, size - inset, size - inset)
        val corner = size * 0.30f
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = stroke
            strokeCap = Paint.Cap.ROUND
            color = context.getColor(R.color.capacity_track)
        }
        canvas.drawRoundRect(rect, corner, corner, paint)
        val used = account.used
        if (used != null && used > 0) {
            val measure = PathMeasure(outline(rect, corner), false)
            val segment = Path()
            measure.getSegment(0f, measure.length * (min(used, 100.0) / 100).toFloat(), segment, true)
            paint.color = signalColor(context, account.signal)
            canvas.drawPath(segment, paint)
        }
        val icon = iconFor(account.provider)
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

    private fun outline(rect: RectF, corner: Float): Path = Path().apply {
        val arc = corner * 2
        moveTo(rect.centerX(), rect.top)
        lineTo(rect.right - corner, rect.top)
        arcTo(RectF(rect.right - arc, rect.top, rect.right, rect.top + arc), 270f, 90f)
        lineTo(rect.right, rect.bottom - corner)
        arcTo(RectF(rect.right - arc, rect.bottom - arc, rect.right, rect.bottom), 0f, 90f)
        lineTo(rect.left + corner, rect.bottom)
        arcTo(RectF(rect.left, rect.bottom - arc, rect.left + arc, rect.bottom), 90f, 90f)
        lineTo(rect.left, rect.top + corner)
        arcTo(RectF(rect.left, rect.top, rect.left + arc, rect.top + arc), 180f, 90f)
        close()
    }

    private fun iconFor(provider: String): Int? = when (provider) {
        "Claude" -> R.drawable.provider_claude
        "Codex" -> R.drawable.provider_codex
        else -> null
    }

    private fun signalColor(context: Context, signal: String): Int = context.getColor(
        when (signal) {
            "red" -> R.color.capacity_signal_red
            "orange" -> R.color.capacity_signal_orange
            "yellow" -> R.color.capacity_signal_yellow
            else -> R.color.capacity_signal_green
        },
    )
}

fun percentText(used: Double?): String = if (used == null) "—" else "${used.toInt()}%"

// The dock's countdown, without the "Resets in" prefix to fit a widget cell.
fun resetText(resetAt: Double?, now: Double = System.currentTimeMillis() / 1000.0): String {
    if (resetAt == null) return ""
    val seconds = (resetAt - now).toLong()
    if (seconds <= 0) return ""
    if (seconds >= 86400) return "${seconds / 86400}d ${(seconds % 86400) / 3600}h"
    if (seconds >= 3600) return "${seconds / 3600}h ${(seconds % 3600) / 60}m"
    return "${maxOf(1, seconds / 60)}m"
}

abstract class CapacityWidget(private val medium: Boolean) : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val views = render(context)
        ids.forEach { manager.updateAppWidget(it, views) }
    }

    private fun render(context: Context): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.capacity_widget)
        views.removeAllViews(R.id.capacity_row_top)
        views.removeAllViews(R.id.capacity_row_bottom)
        val accounts = SnapshotStore.load(context).take(4)
        views.setViewVisibility(R.id.capacity_empty, if (accounts.isEmpty()) View.VISIBLE else View.GONE)
        views.setViewVisibility(R.id.capacity_row_top, if (accounts.isEmpty()) View.GONE else View.VISIBLE)
        views.setViewVisibility(R.id.capacity_row_bottom, if (accounts.isEmpty() || medium || accounts.size < 3) View.GONE else View.VISIBLE)
        accounts.forEachIndexed { index, account ->
            val row = if (medium || index < 2) R.id.capacity_row_top else R.id.capacity_row_bottom
            views.addView(row, cell(context, account))
        }
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
        if (launch != null) {
            val pending = PendingIntent.getActivity(context, 0, launch, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            views.setOnClickPendingIntent(R.id.capacity_root, pending)
        }
        return views
    }

    private fun cell(context: Context, account: WidgetAccount): RemoteViews {
        val cell = RemoteViews(context.packageName, R.layout.capacity_widget_cell)
        cell.setImageViewBitmap(R.id.cell_ring, RingPainter.draw(context, account, if (medium) 46 else 40))
        cell.setTextViewText(R.id.cell_percent, percentText(account.used))
        cell.setViewVisibility(R.id.cell_window, if (medium) View.VISIBLE else View.GONE)
        cell.setViewVisibility(R.id.cell_reset, if (medium) View.VISIBLE else View.GONE)
        cell.setTextViewText(R.id.cell_window, account.window)
        cell.setTextViewText(R.id.cell_reset, resetText(account.resetAt))
        return cell
    }
}

class CapacitySmallWidget : CapacityWidget(medium = false)

class CapacityMediumWidget : CapacityWidget(medium = true)

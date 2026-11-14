package dev.mako.capacity.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PathMeasure
import android.graphics.PorterDuff
import android.graphics.PorterDuffColorFilter
import android.graphics.RectF
import android.net.Uri
import android.view.View
import android.widget.RemoteViews
import android.widget.RemoteViewsService
import dev.mako.capacity.R
import org.json.JSONObject
import kotlin.math.min

data class WidgetAccount(
    val id: String,
    val provider: String,
    val email: String,
    val used: Double?,
    val window: String,
    val resetAt: Double?,
    val state: String,
    val signal: String,
    val available: Boolean,
    val tokens: Double?,
    val costUsd: Double?,
)

// The app writes this snapshot through native/CapacityAndroid/SnapshotBridge.kt.
object SnapshotStore {
    fun load(context: Context): List<WidgetAccount> {
        val text = context.getSharedPreferences("capacity", Context.MODE_PRIVATE).getString("snapshot", null) ?: return emptyList()
        return runCatching {
            val list = JSONObject(text).getJSONArray("accounts")
            (0 until list.length()).map { index ->
                val item = list.getJSONObject(index)
                val used = if (item.isNull("used")) null else item.optDouble("used")
                val state = item.optString("state")
                WidgetAccount(
                    id = item.optString("id"),
                    provider = item.optString("provider"),
                    email = item.optString("email"),
                    used = used,
                    window = item.optString("window"),
                    resetAt = if (item.isNull("resetAt")) null else item.optDouble("resetAt"),
                    state = state,
                    signal = item.optString("signal", "green"),
                    available = if (item.has("available")) item.optBoolean("available") else (used ?: 100.0) < 100 && state == "Available",
                    tokens = if (item.isNull("tokens")) null else item.optDouble("tokens"),
                    costUsd = if (item.isNull("costUsd")) null else item.optDouble("costUsd"),
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

    fun signalColor(context: Context, signal: String): Int = context.getColor(
        when (signal) {
            "red" -> R.color.capacity_signal_red
            "orange" -> R.color.capacity_signal_orange
            "yellow" -> R.color.capacity_signal_yellow
            else -> R.color.capacity_signal_green
        },
    )
}

fun percentText(used: Double?): String = if (used == null) "—" else "${used.toInt()}%"

// The dock's formatCount(): 1.2B, 3.4M, 5.6K.
fun formatCount(value: Double): String = when {
    value >= 1e9 -> String.format(java.util.Locale.US, "%.1fB", value / 1e9)
    value >= 1e6 -> String.format(java.util.Locale.US, "%.1fM", value / 1e6)
    value >= 1e3 -> String.format(java.util.Locale.US, "%.1fK", value / 1e3)
    else -> value.toInt().toString()
}

fun tokenText(tokens: Double?, costUsd: Double?): String =
    if (tokens == null) "" else listOfNotNull("${formatCount(tokens)} tok", costUsd?.let { String.format(java.util.Locale.US, "$%.2f", it) }).joinToString(" · ")

// The dock's countdown, without the "Resets in" prefix to fit a widget row.
fun resetText(resetAt: Double?, now: Double = System.currentTimeMillis() / 1000.0): String {
    if (resetAt == null) return ""
    val seconds = (resetAt - now).toLong()
    if (seconds <= 0) return ""
    if (seconds >= 86400) return "${seconds / 86400}d ${(seconds % 86400) / 3600}h"
    if (seconds >= 3600) return "${seconds / 3600}h ${(seconds % 3600) / 60}m"
    return "${maxOf(1, seconds / 60)}m"
}

fun launchIntent(context: Context): PendingIntent? {
    val launch = context.packageManager.getLaunchIntentForPackage(context.packageName) ?: return null
    return PendingIntent.getActivity(context, 0, launch, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
}

// A scrolling list of accounts, like the dock bar on the Mac. Only "available" and "all" differ.
abstract class AccountsListWidget(private val filter: String, private val title: Int, private val empty: Int) : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        ids.forEach { manager.updateAppWidget(it, render(context, it)) }
        manager.notifyAppWidgetViewDataChanged(ids, R.id.accounts_list)
    }

    private fun render(context: Context, widgetId: Int): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.accounts_list_widget)
        views.setTextViewText(R.id.accounts_title, context.getString(title))
        views.setTextViewText(R.id.accounts_empty, context.getString(empty))
        val accounts = SnapshotStore.load(context)
        val shown = if (filter == "available") accounts.count { it.available } else accounts.size
        views.setTextViewText(R.id.accounts_count, if (accounts.isEmpty()) "" else "$shown of ${accounts.size}")
        val service = Intent(context, AccountsListService::class.java)
            .putExtra(AccountsListService.FILTER, filter)
            .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
        service.data = Uri.parse(service.toUri(Intent.URI_INTENT_SCHEME))
        @Suppress("DEPRECATION")
        views.setRemoteAdapter(R.id.accounts_list, service)
        views.setEmptyView(R.id.accounts_list, R.id.accounts_empty)
        launchIntent(context)?.let {
            views.setOnClickPendingIntent(R.id.accounts_title, it)
            views.setPendingIntentTemplate(R.id.accounts_list, it)
        }
        return views
    }
}

class AvailableAccountsWidget : AccountsListWidget("available", R.string.available_widget_label, R.string.available_widget_empty)

class AllAccountsWidget : AccountsListWidget("all", R.string.all_widget_label, R.string.capacity_widget_empty)

class AccountsListService : RemoteViewsService() {
    override fun onGetViewFactory(intent: Intent): RemoteViewsFactory =
        AccountsListFactory(applicationContext, intent.getStringExtra(FILTER) ?: "all")

    companion object {
        const val FILTER = "filter"
    }
}

class AccountsListFactory(private val context: Context, private val filter: String) : RemoteViewsService.RemoteViewsFactory {
    private var accounts: List<WidgetAccount> = emptyList()
    private var agents: List<WidgetAgent> = emptyList()

    override fun onCreate() = onDataSetChanged()

    override fun onDataSetChanged() {
        val all = SnapshotStore.load(context)
        accounts = if (filter == "available") all.filter { it.available }.sortedBy { it.used ?: 0.0 } else all
        agents = if (filter == "all") AgentSnapshotStore.load(context) else emptyList()
    }

    override fun onDestroy() {
        accounts = emptyList()
        agents = emptyList()
    }

    override fun getCount() = accounts.size + agents.size

    private fun agentRow(agent: WidgetAgent): RemoteViews {
        val row = RemoteViews(context.packageName, R.layout.agents_widget_row)
        row.setImageViewBitmap(R.id.agent_ring, AgentRingPainter.draw(context, agent, 30))
        row.setTextViewText(R.id.agent_heading, agent.heading)
        row.setTextViewText(R.id.agent_step, agent.detail)
        row.setTextViewText(R.id.agent_progress, agent.progress?.let { "${it.toInt()}%" } ?: agent.state)
        row.setTextColor(R.id.agent_progress, AgentRingPainter.colour(context, agent.signal))
        return row
    }

    override fun getViewAt(position: Int): RemoteViews {
        if (position >= accounts.size) {
            val agent = agents.getOrNull(position - accounts.size) ?: return RemoteViews(context.packageName, R.layout.agents_widget_row)
            return agentRow(agent)
        }
        val account = accounts.getOrNull(position) ?: return RemoteViews(context.packageName, R.layout.accounts_list_row)
        val row = RemoteViews(context.packageName, R.layout.accounts_list_row)
        row.setImageViewBitmap(R.id.row_ring, RingPainter.draw(context, account, 36))
        row.setTextViewText(R.id.row_name, account.email.ifEmpty { account.provider })
        val reset = resetText(account.resetAt)
        val detail = listOf(account.provider, account.window, if (reset.isEmpty()) "" else "resets in $reset", tokenText(account.tokens, account.costUsd))
            .filter { it.isNotEmpty() }
            .joinToString(" · ")
        row.setTextViewText(R.id.row_detail, if (account.state == "Available" || account.state.isEmpty()) detail else "${account.state} · $detail")
        row.setTextViewText(R.id.row_percent, percentText(account.used))
        row.setTextColor(R.id.row_percent, RingPainter.signalColor(context, account.signal))
        row.setOnClickFillInIntent(R.id.row_root, Intent())
        return row
    }

    override fun getLoadingView(): RemoteViews? = null

    override fun getViewTypeCount() = 2

    override fun getItemId(position: Int): Long =
        (accounts.getOrNull(position)?.id ?: agents.getOrNull(position - accounts.size)?.id?.let { "agent-$it" })?.hashCode()?.toLong() ?: position.toLong()

    override fun hasStableIds() = true
}

// Every widget the app refreshes when it writes a new snapshot.
val WIDGET_PROVIDERS = listOf(AvailableAccountsWidget::class.java, AllAccountsWidget::class.java, AgentsWidget::class.java)

fun refreshWidgets(context: Context): Int {
    val manager = AppWidgetManager.getInstance(context)
    var placed = 0
    for (provider in WIDGET_PROVIDERS) {
        val component = ComponentName(context, provider)
        val ids = manager.getAppWidgetIds(component)
        if (ids.isEmpty()) continue
        placed += ids.size
        context.sendBroadcast(Intent(AppWidgetManager.ACTION_APPWIDGET_UPDATE).setComponent(component).putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids))
    }
    return placed
}

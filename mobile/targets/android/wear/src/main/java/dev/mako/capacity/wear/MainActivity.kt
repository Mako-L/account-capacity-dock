package dev.mako.capacity.wear

import android.app.Activity
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
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.google.android.gms.wearable.DataClient
import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.Wearable
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.min

// The phone writes the widget snapshot to this Data Layer path; see targets/android/java/WearSync.kt.
const val SNAPSHOT_PATH = "/capacity/snapshot"

// An agent complication sets this so a tap opens the list at the agents.
const val EXTRA_SHOW_AGENTS = "dev.mako.capacity.wear.SHOW_AGENTS"

class MainActivity : Activity(), DataClient.OnDataChangedListener {
    private lateinit var content: LinearLayout
    private var agentsHeader: View? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.main)
        content = findViewById(R.id.content)
        render(SnapshotStore.read(this))
        if (intent.getBooleanExtra(EXTRA_SHOW_AGENTS, false)) showAgents()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.getBooleanExtra(EXTRA_SHOW_AGENTS, false)) showAgents()
    }

    private fun showAgents() {
        val scroll = findViewById<ScrollView>(R.id.scroll)
        // 30dp short of the header keeps it clear of the round screen's edge, like the top of the list.
        scroll.post { agentsHeader?.let { scroll.scrollTo(0, (it.top - dp(30)).coerceAtLeast(0)) } }
    }

    override fun onResume() {
        super.onResume()
        val client = Wearable.getDataClient(this)
        client.addListener(this)
        client.getDataItems(Uri.parse("wear://*$SNAPSHOT_PATH")).addOnSuccessListener { items ->
            val json = items.firstOrNull()?.let { DataMapItem.fromDataItem(it).dataMap.getString("json") }
            items.release()
            if (json != null) update(json)
        }
    }

    override fun onPause() {
        Wearable.getDataClient(this).removeListener(this)
        super.onPause()
    }

    override fun onDataChanged(events: DataEventBuffer) {
        val json = events
            .filter { it.type == DataEvent.TYPE_CHANGED && it.dataItem.uri.path == SNAPSHOT_PATH }
            .lastOrNull()
            ?.let { DataMapItem.fromDataItem(it.dataItem).dataMap.getString("json") }
        events.release()
        if (json != null) runOnUiThread { update(json) }
    }

    private fun update(json: String) {
        SnapshotStore.write(this, json)
        render(json)
    }

    private fun render(json: String?) {
        content.removeAllViews()
        val snapshot = json?.let { runCatching { JSONObject(it) }.getOrNull() }
        agentsHeader = null
        if (snapshot == null) {
            content.addView(text(getString(R.string.empty), R.color.capacity_secondary, 13f))
            return
        }
        val accounts = snapshot.optJSONArray("accounts") ?: JSONArray()
        content.addView(text(getString(R.string.accounts), R.color.capacity_text, 15f))
        if (accounts.length() == 0) content.addView(text(getString(R.string.no_accounts), R.color.capacity_secondary, 12f))
        for (index in 0 until accounts.length()) content.addView(accountRow(accounts.getJSONObject(index)))

        val agents = snapshot.optJSONArray("agents")
        val header = text(getString(R.string.agents), R.color.capacity_text, 15f).apply { setPadding(0, dp(14), 0, dp(4)) }
        agentsHeader = header
        content.addView(header)
        if (agents == null || agents.length() == 0) {
            content.addView(text(getString(if (agents == null) R.string.open_agents else R.string.no_agents), R.color.capacity_secondary, 12f))
        } else {
            for (index in 0 until agents.length()) content.addView(agentRow(agents.getJSONObject(index)))
        }
        val updated = snapshot.optDouble("updatedAt", 0.0)
        if (updated > 0) content.addView(text(getString(R.string.updated, ago(updated)), R.color.capacity_secondary, 11f).apply { setPadding(0, dp(10), 0, 0) })
    }

    private fun accountRow(account: JSONObject): View {
        val used = if (account.isNull("used")) null else account.optDouble("used")
        val signal = account.optString("signal", "green")
        val row = LayoutInflater.from(this).inflate(R.layout.row, content, false)
        row.findViewById<ImageView>(R.id.ring).setImageBitmap(Rings.square(this, used, signal, account.optString("provider"), 32))
        row.findViewById<TextView>(R.id.name).text = account.optString("email").ifEmpty { account.optString("provider") }
        val reset = resetText(if (account.isNull("resetAt")) null else account.optDouble("resetAt"))
        val state = account.optString("state")
        val tokens = if (account.isNull("tokens") || !account.has("tokens")) "" else tokenCount(account.optDouble("tokens")) + " tok"
        row.findViewById<TextView>(R.id.detail).text = listOf(if (state == "Available") "" else state, account.optString("window"), reset, tokens)
            .filter { it.isNotEmpty() }
            .joinToString(" · ")
        row.findViewById<TextView>(R.id.percent).apply {
            this.text = used?.let { "${it.toInt()}%" } ?: "—"
            setTextColor(Rings.colour(this@MainActivity, signal))
        }
        return row
    }

    private fun tokenCount(value: Double): String = when {
        value >= 1e9 -> String.format(java.util.Locale.US, "%.1fB", value / 1e9)
        value >= 1e6 -> String.format(java.util.Locale.US, "%.1fM", value / 1e6)
        value >= 1e3 -> String.format(java.util.Locale.US, "%.1fK", value / 1e3)
        else -> value.toInt().toString()
    }

    private fun agentRow(agent: JSONObject): View {
        val signal = agent.optString("signal", "gray")
        val progress = if (agent.isNull("progress")) null else agent.optDouble("progress")
        val row = LayoutInflater.from(this).inflate(R.layout.row, content, false)
        row.findViewById<ImageView>(R.id.ring).setImageBitmap(Rings.circle(this, agent.optDouble("ring", 0.0), signal, agent.optString("provider"), 32))
        row.findViewById<TextView>(R.id.name).text = agent.optString("label").ifEmpty { agent.optString("name") }.ifEmpty { agent.optString("heading") }
        val subagents = agent.optInt("subagents", 0)
        val running = agent.optInt("runningSubagents", 0)
        val subs = if (subagents == 0) "" else if (running > 0) "$subagents sub, $running running" else "$subagents sub"
        row.findViewById<TextView>(R.id.detail).text = listOf(agent.optString("step").ifEmpty { agent.optString("heading") }, agent.optString("state"), subs)
            .filter { it.isNotEmpty() }
            .joinToString(" · ")
        row.findViewById<TextView>(R.id.percent).apply {
            val count = agent.optJSONArray("stepCount")?.takeIf { it.length() == 2 && it.optInt(1) > 0 }
            this.text = count?.let { "${it.optInt(0)}/${it.optInt(1)}" } ?: progress?.let { "${it.toInt()}%" } ?: ""
            setTextColor(Rings.colour(this@MainActivity, signal))
        }
        return row
    }

    private fun text(value: String, colour: Int, size: Float) = TextView(this).apply {
        this.text = value
        textSize = size
        setTextColor(getColor(colour))
        setPadding(0, dp(2), 0, dp(4))
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}

// The dock's countdown, short: 2d 4h, 3h 20m, 12m.
fun resetText(resetAt: Double?, now: Double = System.currentTimeMillis() / 1000.0): String {
    if (resetAt == null) return ""
    val seconds = (resetAt - now).toLong()
    if (seconds <= 0) return ""
    if (seconds >= 86400) return "${seconds / 86400}d ${(seconds % 86400) / 3600}h"
    if (seconds >= 3600) return "${seconds / 3600}h ${(seconds % 3600) / 60}m"
    return "${maxOf(1, seconds / 60)}m"
}

fun ago(timestamp: Double, now: Double = System.currentTimeMillis() / 1000.0): String {
    val seconds = maxOf(0L, (now - timestamp).toLong())
    if (seconds < 60) return "${seconds}s ago"
    if (seconds < 3600) return "${seconds / 60}m ago"
    if (seconds < 86400) return "${seconds / 3600}h ago"
    return "${seconds / 86400}d ago"
}

// The dock's two ring shapes: a rounded square for quotas, a circle for agents, with the provider mark inside.
object Rings {
    fun square(context: Activity, used: Double?, signal: String, provider: String, sizeDp: Int): Bitmap = draw(context, sizeDp, provider) { canvas, rect, paint ->
        val corner = rect.width() * 0.30f
        canvas.drawRoundRect(rect, corner, corner, paint)
        if (used != null && used > 0) {
            val measure = PathMeasure(roundedOutline(rect, corner), false)
            val segment = Path()
            measure.getSegment(0f, measure.length * (min(used, 100.0) / 100).toFloat(), segment, true)
            paint.color = colour(context, signal)
            canvas.drawPath(segment, paint)
        }
    }

    fun circle(context: Activity, ring: Double, signal: String, provider: String, sizeDp: Int): Bitmap = draw(context, sizeDp, provider) { canvas, rect, paint ->
        canvas.drawOval(rect, paint)
        if (ring > 0) {
            paint.color = colour(context, signal)
            canvas.drawArc(rect, -90f, (min(ring, 100.0) / 100 * 360).toFloat(), false, paint)
        }
    }

    fun colour(context: Activity, signal: String): Int = context.getColor(
        when (signal) {
            "red" -> R.color.capacity_signal_red
            "orange" -> R.color.capacity_signal_orange
            "yellow" -> R.color.capacity_signal_yellow
            "gray" -> R.color.capacity_secondary
            else -> R.color.capacity_signal_green
        },
    )

    private fun draw(context: Activity, sizeDp: Int, provider: String, shape: (Canvas, RectF, Paint) -> Unit): Bitmap {
        val density = context.resources.displayMetrics.density
        val size = (sizeDp * density).toInt()
        val stroke = 3.5f * density
        val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val rect = RectF(stroke / 2, stroke / 2, size - stroke / 2, size - stroke / 2)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = stroke
            strokeCap = Paint.Cap.ROUND
            color = context.getColor(R.color.capacity_track)
        }
        shape(canvas, rect, paint)
        val icon = when (provider) {
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

    private fun roundedOutline(rect: RectF, corner: Float): Path = Path().apply {
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
}

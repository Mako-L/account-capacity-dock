package dev.mako.capacity.wear

import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon
import androidx.wear.watchface.complications.data.ComplicationData
import androidx.wear.watchface.complications.data.ComplicationText
import androidx.wear.watchface.complications.data.ComplicationType
import androidx.wear.watchface.complications.data.MonochromaticImage
import androidx.wear.watchface.complications.data.PlainComplicationText
import androidx.wear.watchface.complications.data.RangedValueComplicationData
import androidx.wear.watchface.complications.data.ShortTextComplicationData
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceUpdateRequester
import androidx.wear.watchface.complications.datasource.ComplicationRequest
import androidx.wear.watchface.complications.datasource.SuspendingComplicationDataSourceService
import org.json.JSONObject

object Complications {
    private val sources = listOf(
        AgentsComplicationService::class.java,
        TopAccount1ComplicationService::class.java,
        TopAccount2ComplicationService::class.java,
        TopAccount3ComplicationService::class.java,
    )

    fun refreshAll(context: Context) {
        for (source in sources) ComplicationDataSourceUpdateRequester.create(context, ComponentName(context, source)).requestUpdateAll()
    }
}

// Every source answers from the stored snapshot and opens the app on tap.
abstract class CapacityComplicationService : SuspendingComplicationDataSourceService() {
    protected abstract val icon: Int

    protected abstract fun build(type: ComplicationType, snapshot: JSONObject?): ComplicationData?

    protected abstract fun previewSnapshot(): JSONObject

    override suspend fun onComplicationRequest(request: ComplicationRequest): ComplicationData? =
        build(request.complicationType, WatchSummary.parse(SnapshotStore.read(this)))

    override fun getPreviewData(type: ComplicationType): ComplicationData? = build(type, previewSnapshot())

    protected fun text(value: String): ComplicationText = PlainComplicationText.Builder(value).build()

    protected fun image() = MonochromaticImage.Builder(Icon.createWithResource(this, icon)).build()

    protected fun openApp(): PendingIntent = PendingIntent.getActivity(
        this,
        0,
        Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    protected fun shortText(value: String, title: String, description: String) =
        ShortTextComplicationData.Builder(text(value), text(description))
            .setTitle(text(title))
            .setMonochromaticImage(image())
            .setTapAction(openApp())
            .build()

    protected fun ranged(value: Float, max: Float, label: String, title: String, description: String) =
        RangedValueComplicationData.Builder(value.coerceIn(0f, max), 0f, max, text(description))
            .setText(text(label))
            .setTitle(text(title))
            .setMonochromaticImage(image())
            .setTapAction(openApp())
            .build()
}

class AgentsComplicationService : CapacityComplicationService() {
    override val icon = R.drawable.ic_complication_agents

    override fun build(type: ComplicationType, snapshot: JSONObject?): ComplicationData? {
        val running = WatchSummary.runningAgents(snapshot)
        val label = running?.toString() ?: "--"
        val title = if (running == 1) getString(R.string.agent_one) else getString(R.string.agent_many)
        val description = getString(R.string.agents_running_description, label)
        return when (type) {
            ComplicationType.SHORT_TEXT -> shortText(label, title, description)
            ComplicationType.RANGED_VALUE -> {
                val total = WatchSummary.totalAgents(snapshot).coerceAtLeast(1)
                ranged((running ?: 0).toFloat(), total.toFloat(), label, title, description)
            }
            else -> null
        }
    }

    override fun previewSnapshot() = JSONObject("""{"agents":[{"status":"working"},{"status":"working"},{"status":"blocked"},{"status":"idle"}]}""")
}

// One source per rank, so a face can show the top three side by side.
abstract class TopAccountComplicationService(private val rank: Int) : CapacityComplicationService() {
    override val icon = R.drawable.ic_complication_account

    override fun build(type: ComplicationType, snapshot: JSONObject?): ComplicationData? {
        val account = WatchSummary.topAccounts(snapshot).getOrNull(rank)
        val label = account?.let { "${it.left}%" } ?: "--"
        val title = account?.label ?: getString(R.string.account_rank, rank + 1)
        val description = getString(R.string.account_left_description, title, label)
        return when (type) {
            ComplicationType.RANGED_VALUE -> ranged((account?.left ?: 0).toFloat(), 100f, label, title, description)
            ComplicationType.SHORT_TEXT -> shortText(label, title, description)
            else -> null
        }
    }

    override fun previewSnapshot() = JSONObject(
        """{"accounts":[{"email":"studio","used":22,"available":true},{"email":"builder","used":12,"available":true},{"email":"review","used":47,"available":true}]}""",
    )
}

class TopAccount1ComplicationService : TopAccountComplicationService(0)
class TopAccount2ComplicationService : TopAccountComplicationService(1)
class TopAccount3ComplicationService : TopAccountComplicationService(2)

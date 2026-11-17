package dev.mako.capacity.wear

import org.json.JSONObject

data class AccountLeft(val label: String, val left: Int, val signal: String)

// done/total when the agent counts steps, else a percentage, else neither.
data class AgentProgress(val label: String, val others: Int, val done: Int?, val total: Int?, val percent: Int?, val state: String) {
    val progressText: String get() = when {
        done != null && total != null -> "$done/$total"
        percent != null -> "$percent%"
        else -> state
    }
}

// What the watch face shows, worked out from the phone's snapshot (see features/capacity/rules.ts toSnapshot).
object WatchSummary {
    const val LABEL_LENGTH = 8
    const val AGENT_LABEL_LENGTH = 12

    fun parse(json: String?): JSONObject? = json?.let { runCatching { JSONObject(it) }.getOrNull() }

    // Working or waiting on you, the phone's isLive rule; null until the phone has sent agents at all.
    fun runningAgents(snapshot: JSONObject?): Int? {
        val agents = snapshot?.optJSONArray("agents") ?: return null
        return (0 until agents.length()).count { agents.getJSONObject(it).optString("status") in setOf("working", "blocked") }
    }

    fun totalAgents(snapshot: JSONObject?): Int = snapshot?.optJSONArray("agents")?.length() ?: 0

    // The first running agent in the phone's order (working before waiting on you), plus how many others run.
    fun topAgent(snapshot: JSONObject?): AgentProgress? {
        val agents = snapshot?.optJSONArray("agents") ?: return null
        val live = (0 until agents.length()).map { agents.getJSONObject(it) }.filter { it.optString("status") in setOf("working", "blocked") }
        val top = live.firstOrNull { it.optString("status") == "working" } ?: live.firstOrNull() ?: return null
        val count = top.optJSONArray("stepCount")?.takeIf { it.length() == 2 }
        val total = count?.optInt(1)?.takeIf { it > 0 }
        val label = top.optString("label").ifEmpty { top.optString("name") }.take(AGENT_LABEL_LENGTH)
        return AgentProgress(
            label = label,
            others = live.size - 1,
            done = total?.let { count?.optInt(0)?.coerceIn(0, it) },
            total = total,
            percent = if (top.isNull("progress") || !top.has("progress")) null else top.optDouble("progress").coerceIn(0.0, 100.0).toInt(),
            state = top.optString("state"),
        )
    }

    // Most capacity left first; accounts that can take work now rank above ones that cannot.
    fun topAccounts(snapshot: JSONObject?, count: Int = 3): List<AccountLeft> {
        val accounts = snapshot?.optJSONArray("accounts") ?: return emptyList()
        return (0 until accounts.length())
            .map { accounts.getJSONObject(it) }
            .filter { !it.isNull("used") && it.has("used") }
            .sortedWith(compareByDescending<JSONObject> { it.optBoolean("available") }.thenBy { it.optDouble("used") })
            .take(count)
            .map { account ->
                val used = account.optDouble("used").coerceIn(0.0, 100.0)
                AccountLeft(label(account), (100 - used).toInt(), account.optString("signal", "green"))
            }
    }

    private fun label(account: JSONObject): String =
        account.optString("email").substringBefore('@').ifEmpty { account.optString("provider") }.take(LABEL_LENGTH)
}

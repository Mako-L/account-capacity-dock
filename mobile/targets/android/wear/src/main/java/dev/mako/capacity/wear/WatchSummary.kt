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

    // Running agents, working ones before those waiting on you, each keeping the phone's order; others counts the rest.
    fun liveAgents(snapshot: JSONObject?): List<AgentProgress> {
        val agents = snapshot?.optJSONArray("agents") ?: return emptyList()
        val live = (0 until agents.length()).map { agents.getJSONObject(it) }.filter { it.optString("status") in setOf("working", "blocked") }
        return live.sortedBy { if (it.optString("status") == "working") 0 else 1 }.map { agent ->
            val count = agent.optJSONArray("stepCount")?.takeIf { it.length() == 2 }
            val total = count?.optInt(1)?.takeIf { it > 0 }
            AgentProgress(
                label = agent.optString("label").ifEmpty { agent.optString("name") }.take(AGENT_LABEL_LENGTH),
                others = live.size - 1,
                done = total?.let { count?.optInt(0)?.coerceIn(0, it) },
                total = total,
                percent = if (agent.isNull("progress") || !agent.has("progress")) null else agent.optDouble("progress").coerceIn(0.0, 100.0).toInt(),
                state = agent.optString("state"),
            )
        }
    }

    fun topAgent(snapshot: JSONObject?): AgentProgress? = liveAgents(snapshot).firstOrNull()

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

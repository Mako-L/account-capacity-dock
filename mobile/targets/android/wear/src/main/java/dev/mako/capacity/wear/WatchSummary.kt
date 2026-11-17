package dev.mako.capacity.wear

import org.json.JSONObject

data class AccountLeft(val label: String, val left: Int, val signal: String)

// What the watch face shows, worked out from the phone's snapshot (see features/capacity/rules.ts toSnapshot).
object WatchSummary {
    const val LABEL_LENGTH = 8

    fun parse(json: String?): JSONObject? = json?.let { runCatching { JSONObject(it) }.getOrNull() }

    // Working or waiting on you, the phone's isLive rule; null until the phone has sent agents at all.
    fun runningAgents(snapshot: JSONObject?): Int? {
        val agents = snapshot?.optJSONArray("agents") ?: return null
        return (0 until agents.length()).count { agents.getJSONObject(it).optString("status") in setOf("working", "blocked") }
    }

    fun totalAgents(snapshot: JSONObject?): Int = snapshot?.optJSONArray("agents")?.length() ?: 0

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

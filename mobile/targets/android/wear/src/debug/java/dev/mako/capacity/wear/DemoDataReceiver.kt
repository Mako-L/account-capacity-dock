package dev.mako.capacity.wear

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import org.json.JSONObject

// Debug builds only: loads made-up accounts and agents so an unpaired emulator can show the face.
class DemoDataReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val now = System.currentTimeMillis() / 1000.0
        val demo = JSONObject(context.assets.open("demo_snapshot.json").bufferedReader().use { it.readText() })
        demo.put("updatedAt", now)
        val accounts = demo.getJSONArray("accounts")
        for (index in 0 until accounts.length()) {
            val account = accounts.getJSONObject(index)
            if (!account.isNull("resetInHours")) account.put("resetAt", now + account.getDouble("resetInHours") * 3600)
        }
        SnapshotStore.write(context, demo.toString())
        resultData = "demo snapshot stored: ${accounts.length()} accounts, ${demo.getJSONArray("agents").length()} agents"
    }
}

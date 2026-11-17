package dev.mako.capacity.widget

import android.content.Context
import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable

// Hands the snapshot to a paired Wear OS watch over the Wearable Data Layer; see targets/wear.
object WearSync {
    const val PATH = "/capacity/snapshot"

    fun push(context: Context, json: String): String = runCatching {
        val request = PutDataMapRequest.create(PATH).apply {
            dataMap.putString("json", json)
            dataMap.putLong("at", System.currentTimeMillis())
        }.asPutDataRequest().setUrgent()
        Wearable.getDataClient(context).putDataItem(request)
        "sent"
    }.getOrDefault("unavailable")
}

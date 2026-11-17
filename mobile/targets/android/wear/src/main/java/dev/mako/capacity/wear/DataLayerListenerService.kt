package dev.mako.capacity.wear

import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.WearableListenerService

// Takes the phone's snapshot even while the app is closed, so the complications stay current.
class DataLayerListenerService : WearableListenerService() {
    override fun onDataChanged(events: DataEventBuffer) {
        val json = events
            .filter { it.type == DataEvent.TYPE_CHANGED && it.dataItem.uri.path == SNAPSHOT_PATH }
            .lastOrNull()
            ?.let { DataMapItem.fromDataItem(it.dataItem).dataMap.getString("json") }
        events.release()
        if (json != null) SnapshotStore.write(this, json)
    }
}

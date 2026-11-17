package dev.mako.capacity.wear

import android.content.Context

// The last snapshot the phone sent; the app screen and every complication read this one copy.
object SnapshotStore {
    private const val PREFS = "capacity"
    private const val KEY = "snapshot"

    fun read(context: Context): String? = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, null)

    fun write(context: Context, json: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY, json).commit()
        Complications.refreshAll(context)
    }
}

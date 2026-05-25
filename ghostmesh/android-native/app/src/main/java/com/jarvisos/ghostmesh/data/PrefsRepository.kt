package com.jarvisos.ghostmesh.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "ghostmesh_prefs")

class PrefsRepository(private val context: Context) {

    companion object {
        val KEY_BACKEND_URL = stringPreferencesKey("backend_url")
        const val DEFAULT_URL = "http://10.0.2.2:8080"
    }

    val backendUrl: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_BACKEND_URL] ?: DEFAULT_URL
    }

    suspend fun setBackendUrl(url: String) {
        context.dataStore.edit { it[KEY_BACKEND_URL] = url.trim() }
        ApiClient.invalidate()
    }
}

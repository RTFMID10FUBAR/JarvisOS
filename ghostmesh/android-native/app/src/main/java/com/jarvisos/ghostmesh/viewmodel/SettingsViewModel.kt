package com.jarvisos.ghostmesh.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.jarvisos.ghostmesh.data.ApiClient
import com.jarvisos.ghostmesh.data.HealthResponse
import com.jarvisos.ghostmesh.data.PrefsRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

sealed class HealthState {
    object Idle : HealthState()
    object Checking : HealthState()
    data class Online(val data: HealthResponse) : HealthState()
    data class Offline(val message: String) : HealthState()
}

class SettingsViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = PrefsRepository(app)

    val backendUrl: StateFlow<String> = prefs.backendUrl.stateIn(
        viewModelScope,
        SharingStarted.WhileSubscribed(5_000),
        PrefsRepository.DEFAULT_URL,
    )

    private val _health = MutableStateFlow<HealthState>(HealthState.Idle)
    val health: StateFlow<HealthState> = _health

    fun saveBackendUrl(url: String) {
        viewModelScope.launch { prefs.setBackendUrl(url) }
    }

    fun checkHealth(baseUrl: String) {
        viewModelScope.launch {
            _health.value = HealthState.Checking
            try {
                val resp = ApiClient.getService(baseUrl).health()
                _health.value = HealthState.Online(resp)
            } catch (e: Exception) {
                _health.value = HealthState.Offline(e.message ?: "Unreachable")
            }
        }
    }
}

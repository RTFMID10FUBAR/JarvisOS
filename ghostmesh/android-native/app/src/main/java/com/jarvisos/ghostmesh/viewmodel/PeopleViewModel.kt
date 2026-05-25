package com.jarvisos.ghostmesh.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jarvisos.ghostmesh.data.ApiClient
import com.jarvisos.ghostmesh.data.PeopleResult
import com.jarvisos.ghostmesh.data.PeopleSearchRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed class PeopleState {
    object Idle : PeopleState()
    object Loading : PeopleState()
    data class Success(val result: PeopleResult) : PeopleState()
    data class Error(val message: String) : PeopleState()
}

class PeopleViewModel : ViewModel() {
    private val _state = MutableStateFlow<PeopleState>(PeopleState.Idle)
    val state: StateFlow<PeopleState> = _state

    fun search(req: PeopleSearchRequest, baseUrl: String) {
        viewModelScope.launch {
            _state.value = PeopleState.Loading
            try {
                val result = ApiClient.getService(baseUrl).peopleSearch(req)
                _state.value = PeopleState.Success(result)
            } catch (e: Exception) {
                _state.value = PeopleState.Error(
                    e.message?.substringAfter(": ") ?: "Could not reach backend"
                )
            }
        }
    }

    fun reset() { _state.value = PeopleState.Idle }
}

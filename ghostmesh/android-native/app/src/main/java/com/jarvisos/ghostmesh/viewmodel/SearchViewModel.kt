package com.jarvisos.ghostmesh.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jarvisos.ghostmesh.data.ApiClient
import com.jarvisos.ghostmesh.data.SearchRequest
import com.jarvisos.ghostmesh.data.SearchResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed class SearchState {
    object Idle : SearchState()
    object Loading : SearchState()
    data class Success(val response: SearchResponse) : SearchState()
    data class Error(val message: String) : SearchState()
}

class SearchViewModel : ViewModel() {
    private val _state = MutableStateFlow<SearchState>(SearchState.Idle)
    val state: StateFlow<SearchState> = _state

    fun search(query: String, engines: List<String>, baseUrl: String) {
        if (query.isBlank() || engines.isEmpty()) return
        viewModelScope.launch {
            _state.value = SearchState.Loading
            try {
                val result = ApiClient.getService(baseUrl)
                    .search(SearchRequest(query = query.trim(), engines = engines))
                _state.value = SearchState.Success(result)
            } catch (e: Exception) {
                _state.value = SearchState.Error(
                    e.message?.substringAfter(": ") ?: "Could not reach backend"
                )
            }
        }
    }

    fun reset() { _state.value = SearchState.Idle }
}

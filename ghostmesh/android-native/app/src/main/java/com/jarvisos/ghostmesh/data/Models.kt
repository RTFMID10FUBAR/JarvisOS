package com.jarvisos.ghostmesh.data

data class SearchRequest(
    val query: String,
    val engines: List<String>,
    val mode: String = "blended",
    val max_results: Int = 20,
)

data class SearchResult(
    val id: String,
    val title: String,
    val snippet: String,
    val url: String,
    val source_engine: String,
    val confidence: Double = 0.0,
    val tags: List<String> = emptyList(),
    val category: String = "",
)

data class SearchResponse(
    val query: String,
    val results: List<SearchResult>,
    val engines_used: List<String>,
    val engines_failed: List<String>,
    val total: Int,
    val duration_ms: Long,
)

data class PeopleSearchRequest(
    val first_name: String? = null,
    val last_name: String? = null,
    val username: String? = null,
    val email: String? = null,
    val phone: String? = null,
    val domain: String? = null,
    val location: String? = null,
)

data class ProfileHit(
    val platform: String,
    val url: String,
    val username: String,
    val category: String,
    val verified: Boolean,
    val http_status: Int,
)

data class PeopleResult(
    val id: String,
    val name: String,
    val confidence: Int,
    val matched_fields: List<String>,
    val profiles: List<ProfileHit>,
    val sources_checked: List<String>,
    val last_checked: String,
    val platforms_found: Int,
    val platforms_checked: Int,
)

data class HealthResponse(
    val api_status: String,
    val configured_engines: List<String> = emptyList(),
    val timestamp: String = "",
)

// ── OSINT Framework ───────────────────────────────────────────────────────────

data class OsintTool(
    val name: String,
    val description: String,
    val url: String,
    val tags: List<String>,
)

data class OsintCategory(
    val id: String,
    val name: String,
    val tools: List<OsintTool>,
)

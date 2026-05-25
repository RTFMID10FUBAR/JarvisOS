package com.jarvisos.ghostmesh.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.jarvisos.ghostmesh.data.SearchResult
import com.jarvisos.ghostmesh.ui.components.*
import com.jarvisos.ghostmesh.ui.theme.*
import com.jarvisos.ghostmesh.viewmodel.SearchState
import com.jarvisos.ghostmesh.viewmodel.SearchViewModel

private data class Engine(val id: String, val label: String, val free: Boolean)
private val ENGINES = listOf(
    Engine("duckduckgo", "DuckDuckGo", true),
    Engine("marginalia",  "Marginalia",  true),
    Engine("urlscan",     "URLScan.io",  true),
    Engine("crtsh",       "Crt.sh",      true),
    Engine("brave",       "Brave",       false),
    Engine("otx",         "OTX",         false),
    Engine("shodan",      "Shodan",      false),
)

@Composable
fun SearchScreen(backendUrl: String, vm: SearchViewModel = viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()
    var query by remember { mutableStateOf("") }
    var selected by remember { mutableStateOf(setOf("duckduckgo", "marginalia", "urlscan")) }
    val keyboard = LocalSoftwareKeyboardController.current

    fun doSearch() {
        keyboard?.hide()
        vm.search(query, selected.toList(), backendUrl)
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
    ) {
        // ── Search bar ────────────────────────────────────────────────────────
        Column(
            modifier = Modifier
                .background(Surface)
                .padding(16.dp)
        ) {
            OutlinedTextField(
                value         = query,
                onValueChange = { query = it },
                modifier      = Modifier.fillMaxWidth(),
                placeholder   = { Text("Search anything…", color = TextMuted) },
                leadingIcon   = { Icon(Icons.Default.Search, null, tint = TextMuted) },
                trailingIcon  = {
                    if (query.isNotEmpty()) {
                        IconButton(onClick = { query = ""; vm.reset() }) {
                            Icon(Icons.Default.Clear, null, tint = TextMuted)
                        }
                    }
                },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { doSearch() }),
                singleLine    = true,
                colors        = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor   = Accent,
                    unfocusedBorderColor = BorderColor,
                    focusedTextColor     = TextPrimary,
                    unfocusedTextColor   = TextPrimary,
                    cursorColor          = Accent,
                ),
            )

            Spacer(Modifier.height(10.dp))

            // Engine chips
            LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                items(ENGINES) { engine ->
                    GmChip(
                        label    = engine.label,
                        selected = engine.id in selected,
                        onClick  = {
                            selected = if (engine.id in selected)
                                selected - engine.id
                            else
                                selected + engine.id
                        },
                    )
                }
            }

            Spacer(Modifier.height(10.dp))

            Button(
                onClick  = { doSearch() },
                modifier = Modifier.fillMaxWidth(),
                enabled  = query.isNotBlank() && selected.isNotEmpty() && state !is SearchState.Loading,
                colors   = ButtonDefaults.buttonColors(containerColor = Accent),
            ) {
                if (state is SearchState.Loading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        color = TextPrimary,
                        strokeWidth = 2.dp,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text("Searching…", color = TextPrimary)
                } else {
                    Icon(Icons.Default.Search, null)
                    Spacer(Modifier.width(6.dp))
                    Text("Search", color = TextPrimary)
                }
            }
        }

        // ── Results ────────────────────────────────────────────────────────────
        when (val s = state) {
            is SearchState.Idle -> {}
            is SearchState.Loading -> {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Accent)
                }
            }
            is SearchState.Error -> {
                LazyColumn(contentPadding = PaddingValues(16.dp)) {
                    item {
                        ErrorCard(s.message)
                    }
                }
            }
            is SearchState.Success -> {
                val real = s.response.results.filter { it.source_engine != "system" }
                if (real.isEmpty()) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text("No results found", color = TextMuted)
                    }
                } else {
                    LazyColumn(
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        item {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    "${real.size} results",
                                    style = MaterialTheme.typography.labelMedium,
                                    color = TextMuted,
                                )
                                Text(
                                    "${s.response.duration_ms}ms · ${s.response.engines_used.joinToString(", ")}",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = TextMuted,
                                )
                            }
                        }
                        items(real) { result ->
                            SearchResultCard(result)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SearchResultCard(result: SearchResult) {
    val context = LocalContext.current
    GmCard(
        modifier = Modifier.clickable {
            if (result.url != "#") {
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(result.url)))
            }
        }
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text  = result.source_engine,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                color = Accent,
                modifier = Modifier
                    .clip(RoundedCornerShape(4.dp))
                    .background(AccentBg)
                    .border(1.dp, Accent.copy(0.3f), RoundedCornerShape(4.dp))
                    .padding(horizontal = 6.dp, vertical = 2.dp),
            )
            if (result.confidence > 0) {
                Text(
                    text  = "${"%.0f".format(result.confidence * 100)}%",
                    fontSize = 10.sp,
                    color = TextMuted,
                )
            }
        }

        Spacer(Modifier.height(6.dp))

        Text(
            text  = result.title,
            style = MaterialTheme.typography.titleSmall,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )

        if (result.snippet.isNotBlank()) {
            Spacer(Modifier.height(4.dp))
            Text(
                text  = result.snippet,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
            )
        }

        if (result.url != "#") {
            Spacer(Modifier.height(6.dp))
            Text(
                text  = result.url,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
                color = Accent,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

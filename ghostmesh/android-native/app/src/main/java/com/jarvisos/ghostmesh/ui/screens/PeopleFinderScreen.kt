package com.jarvisos.ghostmesh.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.jarvisos.ghostmesh.data.PeopleSearchRequest
import com.jarvisos.ghostmesh.data.ProfileHit
import com.jarvisos.ghostmesh.ui.components.*
import com.jarvisos.ghostmesh.ui.theme.*
import com.jarvisos.ghostmesh.viewmodel.PeopleState
import com.jarvisos.ghostmesh.viewmodel.PeopleViewModel

@Composable
fun PeopleFinderScreen(backendUrl: String, vm: PeopleViewModel = viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()

    var firstName by remember { mutableStateOf("") }
    var lastName  by remember { mutableStateOf("") }
    var username  by remember { mutableStateOf("") }
    var email     by remember { mutableStateOf("") }
    var phone     by remember { mutableStateOf("") }
    var domain    by remember { mutableStateOf("") }
    var location  by remember { mutableStateOf("") }

    val anyFilled = listOf(firstName, lastName, username, email, phone, domain, location)
        .any { it.isNotBlank() }

    fun doSearch() {
        vm.search(
            PeopleSearchRequest(
                first_name = firstName.trim().ifBlank { null },
                last_name  = lastName.trim().ifBlank { null },
                username   = username.trim().ifBlank { null },
                email      = email.trim().ifBlank { null },
                phone      = phone.trim().ifBlank { null },
                domain     = domain.trim().ifBlank { null },
                location   = location.trim().ifBlank { null },
            ),
            backendUrl,
        )
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(Background),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // ── Header ────────────────────────────────────────────────────────────
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Person, null, tint = Accent, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text("People Finder", style = MaterialTheme.typography.titleLarge)
            }
        }

        item {
            Text(
                "Searches publicly available profiles across 20+ platforms. " +
                "No private data access.",
                style = MaterialTheme.typography.bodySmall,
            )
        }

        // ── Search form ────────────────────────────────────────────────────────
        item {
            GmCard {
                val fields = listOf(
                    Triple("First Name", firstName) { v: String -> firstName = v },
                    Triple("Last Name",  lastName)  { v: String -> lastName = v },
                    Triple("Username / Handle", username) { v: String -> username = v },
                    Triple("Email",  email)  { v: String -> email = v },
                    Triple("Phone",  phone)  { v: String -> phone = v },
                    Triple("Domain", domain) { v: String -> domain = v },
                    Triple("City / State / Country", location) { v: String -> location = v },
                )
                fields.forEach { (label, value, setter) ->
                    OutlinedTextField(
                        value         = value,
                        onValueChange = setter,
                        label         = { Text(label, fontSize = 12.sp) },
                        modifier      = Modifier.fillMaxWidth(),
                        singleLine    = true,
                        colors        = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor   = Accent,
                            unfocusedBorderColor = BorderColor,
                            focusedTextColor     = TextPrimary,
                            unfocusedTextColor   = TextPrimary,
                            focusedLabelColor    = Accent,
                            unfocusedLabelColor  = TextMuted,
                            cursorColor          = Accent,
                        ),
                    )
                    Spacer(Modifier.height(8.dp))
                }

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick  = { doSearch() },
                        modifier = Modifier.weight(1f),
                        enabled  = anyFilled && state !is PeopleState.Loading,
                        colors   = ButtonDefaults.buttonColors(containerColor = Accent),
                    ) {
                        if (state is PeopleState.Loading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                color = TextPrimary,
                                strokeWidth = 2.dp,
                            )
                            Spacer(Modifier.width(6.dp))
                            Text("Checking 20 platforms…", color = TextPrimary)
                        } else {
                            Text("Search", color = TextPrimary)
                        }
                    }
                    OutlinedButton(
                        onClick = {
                            firstName = ""; lastName = ""; username = ""
                            email = ""; phone = ""; domain = ""; location = ""
                            vm.reset()
                        },
                        border = ButtonDefaults.outlinedButtonBorder.copy(
                            brush = androidx.compose.ui.graphics.SolidColor(BorderColor)
                        ),
                    ) { Text("Clear", color = TextMuted) }
                }
            }
        }

        // ── Results ────────────────────────────────────────────────────────────
        when (val s = state) {
            is PeopleState.Idle    -> {}
            is PeopleState.Loading -> {}
            is PeopleState.Error   -> item { ErrorCard(s.message) }
            is PeopleState.Success -> {
                val result = s.result
                item {
                    GmCard {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column {
                                Text(result.name, style = MaterialTheme.typography.titleMedium)
                                Spacer(Modifier.height(4.dp))
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    ConfidenceBadge(result.confidence)
                                    Text(
                                        "${result.platforms_found} / ${result.platforms_checked} platforms",
                                        fontSize = 11.sp,
                                        color = Teal,
                                    )
                                }
                            }
                        }

                        if (result.matched_fields.isNotEmpty()) {
                            Spacer(Modifier.height(10.dp))
                            SectionLabel("Matched Fields")
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                modifier = Modifier.fillMaxWidth(),
                            ) {
                                result.matched_fields.forEach { field ->
                                    Text(
                                        text = field,
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = Accent,
                                        modifier = Modifier
                                            .clip(RoundedCornerShape(99.dp))
                                            .background(AccentBg)
                                            .border(1.dp, Accent.copy(0.25f), RoundedCornerShape(99.dp))
                                            .padding(horizontal = 8.dp, vertical = 2.dp),
                                    )
                                }
                            }
                        }
                    }
                }

                if (result.profiles.isEmpty()) {
                    item { EmptyCard("No public profiles found on checked platforms.") }
                } else {
                    item { SectionLabel("Public Profiles (${result.profiles.size})") }
                    items(result.profiles) { profile -> ProfileRow(profile) }
                }
            }
        }
    }
}

@Composable
private fun ProfileRow(profile: ProfileHit) {
    val context = LocalContext.current
    GmCard {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(profile.platform, style = MaterialTheme.typography.titleSmall)
                Text(
                    "@${profile.username}",
                    fontSize = 12.sp,
                    color = TextMuted,
                    fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace,
                )
            }
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = profile.category,
                    fontSize = 10.sp,
                    color = TextMuted,
                    modifier = Modifier
                        .clip(RoundedCornerShape(4.dp))
                        .background(SurfaceVar)
                        .padding(horizontal = 6.dp, vertical = 2.dp),
                )
                IconButton(
                    onClick = {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(profile.url)))
                    },
                    modifier = Modifier.size(32.dp),
                ) {
                    Icon(Icons.Default.OpenInNew, null, tint = Accent, modifier = Modifier.size(16.dp))
                }
            }
        }
    }
}

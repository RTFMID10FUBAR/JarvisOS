package com.jarvisos.ghostmesh.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jarvisos.ghostmesh.ui.components.GmCard
import com.jarvisos.ghostmesh.ui.components.SectionLabel
import com.jarvisos.ghostmesh.ui.components.StatusDot
import com.jarvisos.ghostmesh.ui.theme.*
import com.jarvisos.ghostmesh.viewmodel.HealthState
import com.jarvisos.ghostmesh.viewmodel.SettingsViewModel

@Composable
fun SettingsScreen(vm: SettingsViewModel) {
    val backendUrl by vm.backendUrl.collectAsStateWithLifecycle()
    val health     by vm.health.collectAsStateWithLifecycle()

    var urlInput by remember(backendUrl) { mutableStateOf(backendUrl) }
    var saved    by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Settings, null, tint = Accent, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text("Settings", style = MaterialTheme.typography.titleLarge)
        }

        // ── Backend connection ─────────────────────────────────────────────────
        GmCard {
            SectionLabel("Backend URL")
            Text(
                "Enter the URL of your GhostMesh backend. " +
                "On the same WiFi as your Mac, use its LAN IP (e.g. 192.168.1.42:8080). " +
                "For emulator use 10.0.2.2:8080.",
                style = MaterialTheme.typography.bodySmall,
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value         = urlInput,
                onValueChange = { urlInput = it; saved = false },
                label         = { Text("Backend URL") },
                placeholder   = { Text("http://192.168.1.42:8080") },
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
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = {
                        vm.saveBackendUrl(urlInput.trim())
                        saved = true
                    },
                    colors   = ButtonDefaults.buttonColors(containerColor = Accent),
                ) {
                    if (saved) {
                        Icon(Icons.Default.Check, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Saved", color = TextPrimary)
                    } else {
                        Text("Save", color = TextPrimary)
                    }
                }
                OutlinedButton(
                    onClick = { vm.checkHealth(urlInput.trim().ifBlank { backendUrl }) },
                    enabled = health !is HealthState.Checking,
                ) {
                    if (health is HealthState.Checking) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(14.dp),
                            color = Accent,
                            strokeWidth = 2.dp,
                        )
                        Spacer(Modifier.width(4.dp))
                    }
                    Text("Test Connection", color = Accent)
                }
            }

            when (val h = health) {
                is HealthState.Online -> {
                    Spacer(Modifier.height(8.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        StatusDot(online = true)
                        Spacer(Modifier.width(6.dp))
                        Text("Connected — ${h.data.api_status}", fontSize = 12.sp, color = Teal)
                    }
                    if (h.data.configured_engines.isNotEmpty()) {
                        Text(
                            "Engines: ${h.data.configured_engines.joinToString(", ")}",
                            fontSize = 11.sp, color = TextMuted,
                        )
                    }
                }
                is HealthState.Offline -> {
                    Spacer(Modifier.height(8.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        StatusDot(online = false)
                        Spacer(Modifier.width(6.dp))
                        Text("Offline — ${h.message}", fontSize = 12.sp, color = RedColor)
                    }
                }
                else -> {}
            }
        }

        // ── About ─────────────────────────────────────────────────────────────
        GmCard {
            SectionLabel("About")
            InfoRow("App", "JarvisOS GhostMesh")
            InfoRow("Version", "0.1.0")
            InfoRow("Platform", "Android (Kotlin + Jetpack Compose)")
            InfoRow("Backend", "GhostMesh FastAPI")
            Spacer(Modifier.height(8.dp))
            Text(
                "Passive OSINT only. No private data access, no login bypass, " +
                "no credential storage. All searches are transparent and auditable.",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = TextMuted)
        Text(value, style = MaterialTheme.typography.bodySmall, color = TextPrimary)
    }
    HorizontalDivider(color = BorderColor.copy(alpha = 0.4f), thickness = 0.5.dp)
}

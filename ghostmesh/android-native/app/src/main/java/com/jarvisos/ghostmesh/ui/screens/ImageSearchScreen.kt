package com.jarvisos.ghostmesh.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.OpenInBrowser
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.jarvisos.ghostmesh.ui.components.GmCard
import com.jarvisos.ghostmesh.ui.components.GmChip
import com.jarvisos.ghostmesh.ui.components.SectionLabel
import com.jarvisos.ghostmesh.ui.theme.*
import java.net.URLEncoder

private data class RevEngine(
    val id: String,
    val name: String,
    val buildUrl: (String) -> String,
)

private val REV_ENGINES = listOf(
    RevEngine("google", "Google Images") { url ->
        "https://images.google.com/searchbyimage?image_url=${enc(url)}"
    },
    RevEngine("yandex", "Yandex Images") { url ->
        "https://yandex.com/images/search?url=${enc(url)}&rpt=imageview"
    },
    RevEngine("tineye", "TinEye") { url ->
        "https://tineye.com/search?url=${enc(url)}"
    },
    RevEngine("bing", "Bing Visual") { url ->
        "https://www.bing.com/images/search?view=detailv2&imageurl=${enc(url)}&form=SBIVSP"
    },
    RevEngine("pimeyes", "PimEyes (Face)") { url ->
        "https://pimeyes.com/en"
    },
)

private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")

@Composable
fun ImageSearchScreen() {
    val context = LocalContext.current
    var imageUrl  by remember { mutableStateOf("") }
    var selected  by remember { mutableStateOf(setOf("google", "yandex", "tineye")) }
    var launched  by remember { mutableStateOf(0) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Image, null, tint = Accent, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text("Reverse Image Search", style = MaterialTheme.typography.titleLarge)
        }

        Text(
            "Paste an image URL to open it in one or more reverse image engines. " +
            "Results open in your browser.",
            style = MaterialTheme.typography.bodySmall,
        )

        GmCard {
            OutlinedTextField(
                value         = imageUrl,
                onValueChange = { imageUrl = it; launched = 0 },
                label         = { Text("Image URL") },
                placeholder   = { Text("https://example.com/image.jpg") },
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
        }

        GmCard {
            SectionLabel("Engines")
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                REV_ENGINES.forEach { engine ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Checkbox(
                            checked = engine.id in selected,
                            onCheckedChange = { checked ->
                                selected = if (checked) selected + engine.id else selected - engine.id
                            },
                            colors = CheckboxDefaults.colors(
                                checkedColor   = Accent,
                                uncheckedColor = BorderColor,
                            ),
                        )
                        Spacer(Modifier.width(6.dp))
                        Text(engine.name, style = MaterialTheme.typography.bodyMedium, color = TextPrimary)
                    }
                }
            }
        }

        Button(
            onClick = {
                val url = imageUrl.trim()
                if (url.isBlank()) return@Button
                var count = 0
                REV_ENGINES.filter { it.id in selected }.forEach { engine ->
                    val link = engine.buildUrl(url)
                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(link)).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    })
                    count++
                }
                launched = count
            },
            modifier = Modifier.fillMaxWidth(),
            enabled  = imageUrl.isNotBlank() && selected.isNotEmpty(),
            colors   = ButtonDefaults.buttonColors(containerColor = Accent),
        ) {
            Icon(Icons.Default.OpenInBrowser, null)
            Spacer(Modifier.width(6.dp))
            Text(
                if (selected.isEmpty()) "Select at least one engine"
                else "Open in ${selected.size} engine${if (selected.size != 1) "s" else ""}",
                color = TextPrimary,
            )
        }

        if (launched > 0) {
            GmCard {
                Text(
                    "Opened $launched browser tab${if (launched != 1) "s" else ""}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Teal,
                )
            }
        }
    }
}

package com.jarvisos.ghostmesh.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvisos.ghostmesh.data.OSINT_CATEGORIES
import com.jarvisos.ghostmesh.data.OsintCategory
import com.jarvisos.ghostmesh.data.OsintTool
import com.jarvisos.ghostmesh.ui.theme.*

@Composable
fun FrameworkScreen() {
    var query    by remember { mutableStateOf("") }
    val expanded = remember { mutableStateMapOf<String, Boolean>().apply {
        OSINT_CATEGORIES.forEach { put(it.id, true) }
    }}

    val filtered = remember(query) {
        if (query.isBlank()) OSINT_CATEGORIES
        else OSINT_CATEGORIES.mapNotNull { cat ->
            val tools = cat.tools.filter { tool ->
                query.lowercase().let { q ->
                    tool.name.lowercase().contains(q) ||
                    tool.description.lowercase().contains(q) ||
                    tool.tags.any { it.contains(q) }
                }
            }
            if (tools.isEmpty()) null else cat.copy(tools = tools)
        }
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(Background),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            OutlinedTextField(
                value         = query,
                onValueChange = { query = it },
                modifier      = Modifier.fillMaxWidth(),
                placeholder   = { Text("Search tools…", color = TextMuted) },
                leadingIcon   = { Icon(Icons.Default.Search, null, tint = TextMuted) },
                singleLine    = true,
                colors        = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor   = Accent,
                    unfocusedBorderColor = BorderColor,
                    focusedTextColor     = TextPrimary,
                    unfocusedTextColor   = TextPrimary,
                    cursorColor          = Accent,
                ),
            )
        }

        item {
            val total = filtered.sumOf { it.tools.size }
            Text(
                "$total tools across ${filtered.size} categories",
                fontSize = 11.sp,
                color = TextMuted,
            )
        }

        items(filtered) { category ->
            CategorySection(
                category = category,
                isExpanded = expanded[category.id] ?: true,
                onToggle = { expanded[category.id] = !(expanded[category.id] ?: true) },
            )
        }
    }
}

@Composable
private fun CategorySection(
    category: OsintCategory,
    isExpanded: Boolean,
    onToggle: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(Surface)
            .border(1.dp, BorderColor, RoundedCornerShape(10.dp))
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { onToggle() }
                .padding(14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(category.name, style = MaterialTheme.typography.titleSmall)
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text("${category.tools.size}", fontSize = 11.sp, color = TextMuted)
                Icon(
                    if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    null,
                    tint = TextMuted,
                    modifier = Modifier.size(18.dp),
                )
            }
        }

        AnimatedVisibility(visible = isExpanded) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp),
            ) {
                HorizontalDivider(color = BorderColor, thickness = 1.dp)
                category.tools.forEach { tool ->
                    ToolRow(tool)
                }
            }
        }
    }
}

@Composable
private fun ToolRow(tool: OsintTool) {
    val context = LocalContext.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable {
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(tool.url)))
            }
            .padding(horizontal = 14.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(tool.name, style = MaterialTheme.typography.titleSmall)
            Spacer(Modifier.height(3.dp))
            Text(
                tool.description,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                tool.tags.take(3).forEach { tag ->
                    Text(
                        text = tag,
                        fontSize = 10.sp,
                        color = if (tag == "free") Teal else if (tag == "paid") Yellow else TextMuted,
                        modifier = Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .background(SurfaceVar)
                            .border(
                                1.dp,
                                if (tag == "free") Teal.copy(0.3f)
                                else if (tag == "paid") Yellow.copy(0.3f)
                                else BorderColor,
                                RoundedCornerShape(4.dp)
                            )
                            .padding(horizontal = 5.dp, vertical = 1.dp),
                    )
                }
            }
        }
        Icon(
            Icons.Default.OpenInNew,
            null,
            tint = TextMuted,
            modifier = Modifier.size(16.dp).padding(top = 2.dp),
        )
    }
    HorizontalDivider(
        modifier = Modifier.padding(horizontal = 14.dp),
        color = BorderColor.copy(alpha = 0.4f),
        thickness = 0.5.dp,
    )
}

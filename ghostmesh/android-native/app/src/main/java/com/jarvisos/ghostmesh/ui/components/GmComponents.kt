package com.jarvisos.ghostmesh.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvisos.ghostmesh.ui.theme.*

@Composable
fun GmCard(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(Surface)
            .border(1.dp, BorderColor, RoundedCornerShape(10.dp))
            .padding(14.dp),
        content = content,
    )
}

@Composable
fun GmChip(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val bg    = if (selected) AccentBg  else SurfaceVar
    val fg    = if (selected) Accent    else TextMuted
    val border = if (selected) Accent.copy(alpha = 0.4f) else BorderColor

    FilterChip(
        selected  = selected,
        onClick   = onClick,
        label     = { Text(label, fontSize = 12.sp) },
        modifier  = modifier,
        colors    = FilterChipDefaults.filterChipColors(
            containerColor         = bg,
            selectedContainerColor = bg,
            labelColor             = fg,
            selectedLabelColor     = fg,
        ),
        border = FilterChipDefaults.filterChipBorder(
            enabled        = true,
            selected       = selected,
            borderColor    = border,
            selectedBorderColor = border,
        ),
    )
}

@Composable
fun StatusDot(online: Boolean, modifier: Modifier = Modifier) {
    val color = if (online) Teal else RedColor
    Box(
        modifier = modifier
            .size(8.dp)
            .clip(RoundedCornerShape(50))
            .background(color)
    )
}

@Composable
fun SectionLabel(text: String) {
    Text(
        text     = text.uppercase(),
        fontSize = 10.sp,
        fontWeight = FontWeight.Bold,
        color    = TextMuted,
        letterSpacing = 0.08.sp,
        modifier = Modifier.padding(bottom = 8.dp),
    )
}

@Composable
fun ConfidenceBadge(score: Int) {
    val (bg, fg) = when {
        score >= 75 -> TealBg   to Teal
        score >= 45 -> YellowBg to Yellow
        else        -> AccentBg to Accent
    }
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(bg)
            .border(1.dp, fg.copy(alpha = 0.3f), RoundedCornerShape(4.dp))
            .padding(horizontal = 8.dp, vertical = 2.dp)
    ) {
        Text("$score%", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = fg)
    }
}

@Composable
fun ErrorCard(message: String, onRetry: (() -> Unit)? = null) {
    GmCard {
        Text("Connection error", style = MaterialTheme.typography.titleSmall, color = RedColor)
        Spacer(Modifier.height(4.dp))
        Text(message, style = MaterialTheme.typography.bodySmall)
        if (onRetry != null) {
            Spacer(Modifier.height(10.dp))
            Button(
                onClick = onRetry,
                colors = ButtonDefaults.buttonColors(containerColor = SurfaceVar),
            ) { Text("Retry", color = TextSecondary) }
        }
    }
}

@Composable
fun EmptyCard(message: String) {
    GmCard {
        Box(
            modifier = Modifier.fillMaxWidth().padding(vertical = 16.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(message, style = MaterialTheme.typography.bodyMedium, color = TextMuted)
        }
    }
}

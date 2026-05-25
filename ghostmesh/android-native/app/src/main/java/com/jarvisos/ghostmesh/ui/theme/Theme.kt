package com.jarvisos.ghostmesh.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val DarkColors = darkColorScheme(
    primary          = Accent,
    onPrimary        = TextPrimary,
    primaryContainer = AccentDim,
    background       = Background,
    surface          = Surface,
    surfaceVariant   = SurfaceVar,
    onBackground     = TextPrimary,
    onSurface        = TextPrimary,
    onSurfaceVariant = TextSecondary,
    outline          = BorderColor,
    outlineVariant   = BorderColor,
    error            = RedColor,
    secondary        = Teal,
    onSecondary      = Background,
    tertiary         = Yellow,
)

@Composable
fun GhostMeshTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColors,
        typography  = Typography,
        content     = content,
    )
}

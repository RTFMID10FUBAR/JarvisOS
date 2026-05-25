package com.jarvisos.ghostmesh.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val Typography = Typography(
    headlineMedium = TextStyle(fontWeight = FontWeight.Bold,     fontSize = 22.sp, color = TextPrimary),
    headlineSmall  = TextStyle(fontWeight = FontWeight.Bold,     fontSize = 20.sp, color = TextPrimary),
    titleLarge     = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 18.sp, color = TextPrimary),
    titleMedium    = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = TextPrimary),
    titleSmall     = TextStyle(fontWeight = FontWeight.Medium,   fontSize = 14.sp, color = TextPrimary),
    bodyLarge      = TextStyle(fontWeight = FontWeight.Normal,   fontSize = 16.sp, color = TextSecondary),
    bodyMedium     = TextStyle(fontWeight = FontWeight.Normal,   fontSize = 14.sp, color = TextSecondary),
    bodySmall      = TextStyle(fontWeight = FontWeight.Normal,   fontSize = 12.sp, color = TextMuted),
    labelMedium    = TextStyle(fontWeight = FontWeight.Medium,   fontSize = 12.sp, color = TextSecondary),
    labelSmall     = TextStyle(fontFamily = FontFamily.Monospace, fontSize = 11.sp, color = TextMuted),
)

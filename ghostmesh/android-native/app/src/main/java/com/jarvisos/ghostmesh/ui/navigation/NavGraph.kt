package com.jarvisos.ghostmesh.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Shield
import androidx.compose.ui.graphics.vector.ImageVector

sealed class Screen(val route: String, val label: String, val icon: ImageVector) {
    object Search    : Screen("search",    "Search",    Icons.Default.Search)
    object People    : Screen("people",    "People",    Icons.Default.Person)
    object Images    : Screen("images",    "Images",    Icons.Default.Image)
    object Framework : Screen("framework", "Framework", Icons.Default.Shield)
    object Settings  : Screen("settings",  "Settings",  Icons.Default.Settings)
}

val BOTTOM_NAV_ITEMS = listOf(
    Screen.Search,
    Screen.People,
    Screen.Images,
    Screen.Framework,
    Screen.Settings,
)

package com.jarvisos.ghostmesh.ui

import android.app.Application
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.jarvisos.ghostmesh.ui.navigation.BOTTOM_NAV_ITEMS
import com.jarvisos.ghostmesh.ui.navigation.Screen
import com.jarvisos.ghostmesh.ui.screens.*
import com.jarvisos.ghostmesh.ui.theme.Background
import com.jarvisos.ghostmesh.ui.theme.BorderColor
import com.jarvisos.ghostmesh.ui.theme.Surface
import com.jarvisos.ghostmesh.viewmodel.PeopleViewModel
import com.jarvisos.ghostmesh.viewmodel.SearchViewModel
import com.jarvisos.ghostmesh.viewmodel.SettingsViewModel

@Composable
fun GhostMeshApp() {
    val context = LocalContext.current
    val app = context.applicationContext as Application

    val settingsVm: SettingsViewModel = viewModel(
        factory = object : androidx.lifecycle.ViewModelProvider.Factory {
            override fun <T : androidx.lifecycle.ViewModel> create(modelClass: Class<T>): T {
                @Suppress("UNCHECKED_CAST")
                return SettingsViewModel(app) as T
            }
        }
    )
    val searchVm: SearchViewModel   = viewModel()
    val peopleVm: PeopleViewModel   = viewModel()

    val backendUrl by settingsVm.backendUrl.collectAsStateWithLifecycle()
    val navController = rememberNavController()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    Scaffold(
        containerColor = Background,
        contentColor   = androidx.compose.ui.graphics.Color.Unspecified,
        bottomBar = {
            Column {
                HorizontalDivider(color = BorderColor, thickness = 1.dp)
                NavigationBar(
                    containerColor = Surface,
                    tonalElevation = 0.dp,
                ) {
                    BOTTOM_NAV_ITEMS.forEach { screen ->
                        NavigationBarItem(
                            selected = currentRoute == screen.route,
                            onClick = {
                                navController.navigate(screen.route) {
                                    popUpTo(navController.graph.startDestinationId) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon  = { Icon(screen.icon, contentDescription = screen.label) },
                            label = { Text(screen.label) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor   = com.jarvisos.ghostmesh.ui.theme.Accent,
                                selectedTextColor   = com.jarvisos.ghostmesh.ui.theme.Accent,
                                unselectedIconColor = com.jarvisos.ghostmesh.ui.theme.TextMuted,
                                unselectedTextColor = com.jarvisos.ghostmesh.ui.theme.TextMuted,
                                indicatorColor      = com.jarvisos.ghostmesh.ui.theme.AccentBg,
                            ),
                        )
                    }
                }
            }
        },
    ) { innerPadding ->
        NavHost(
            navController    = navController,
            startDestination = Screen.Search.route,
            modifier         = Modifier.padding(innerPadding),
        ) {
            composable(Screen.Search.route)    { SearchScreen(backendUrl = backendUrl, vm = searchVm) }
            composable(Screen.People.route)    { PeopleFinderScreen(backendUrl = backendUrl, vm = peopleVm) }
            composable(Screen.Images.route)    { ImageSearchScreen() }
            composable(Screen.Framework.route) { FrameworkScreen() }
            composable(Screen.Settings.route)  { SettingsScreen(vm = settingsVm) }
        }
    }
}

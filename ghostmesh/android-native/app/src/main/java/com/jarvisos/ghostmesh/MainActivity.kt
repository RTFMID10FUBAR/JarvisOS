package com.jarvisos.ghostmesh

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.jarvisos.ghostmesh.ui.GhostMeshApp
import com.jarvisos.ghostmesh.ui.theme.GhostMeshTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            GhostMeshTheme {
                GhostMeshApp()
            }
        }
    }
}

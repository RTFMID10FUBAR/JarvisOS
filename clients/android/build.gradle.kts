// Root build. The version catalog is deliberately small: the core module has
// zero third-party dependencies, which is what lets it be compiled and tested
// with nothing but the Kotlin compiler (see tools/build-core.sh).
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.jvm") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
}

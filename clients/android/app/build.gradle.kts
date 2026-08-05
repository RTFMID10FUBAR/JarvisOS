// The Android app. Needs the SDK; cannot be built in an environment without it.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "casecommand.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "casecommand.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
    }

    // Sign with a stable key when one is provided.
    //
    // Without this, Gradle signs debug builds with a keystore it generates on
    // the spot if none exists. On a CI runner none ever exists, so every build
    // got a different key — and Android will not install an APK over one signed
    // with a different key. Every update therefore meant uninstall, which wipes
    // the record held on the device and the paired token, which meant entering
    // a pairing code again. Every single time.
    //
    // The key is passed by environment rather than committed: this repository
    // is public, and a signing key in it would let anyone build an APK that
    // Android would accept as an update to this app.
    signingConfigs {
        create("stable") {
            val keystore = System.getenv("ANDROID_KEYSTORE_PATH")
            if (!keystore.isNullOrBlank()) {
                storeFile = file(keystore)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS") ?: "casecommand"
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
                    ?: System.getenv("ANDROID_KEYSTORE_PASSWORD")
            }
        }
    }

    buildFeatures { compose = true }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    sourceSets["main"].java.srcDirs("src/main/kotlin")

    buildTypes {
        debug {
            // Only override when a key was actually supplied; otherwise fall
            // back to Gradle's generated debug key so a plain checkout still
            // builds. CI prints the resulting fingerprint either way.
            if (!System.getenv("ANDROID_KEYSTORE_PATH").isNullOrBlank()) {
                signingConfig = signingConfigs.getByName("stable")
            }
        }
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
            if (!System.getenv("ANDROID_KEYSTORE_PATH").isNullOrBlank()) {
                signingConfig = signingConfigs.getByName("stable")
            }
        }
    }
}

dependencies {
    implementation(project(":core"))
    implementation(platform("androidx.compose:compose-bom:2024.09.03"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}

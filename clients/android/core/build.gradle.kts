// The protocol core: pure Kotlin/JVM, no Android, no third-party dependencies.
//
// Being a plain JVM module is the point. It means the sync engine, the local
// store contract, and all twelve conformance rules can be compiled and run
// without an emulator and without the Android SDK — which is what makes them
// testable in CI at all.
plugins { id("org.jetbrains.kotlin.jvm") }

kotlin { jvmToolchain(17) }

sourceSets {
    named("main") { java.srcDirs("src/main/kotlin") }
}

tasks.register<JavaExec>("selfTest") {
    description = "Run the core self test, and the conformance rules if a server is given."
    group = "verification"
    mainClass.set("casecommand.core.MainKt")
    classpath = sourceSets["main"].runtimeClasspath
    // ./gradlew :core:selfTest --args="http://127.0.0.1:8787 ABC123"
}

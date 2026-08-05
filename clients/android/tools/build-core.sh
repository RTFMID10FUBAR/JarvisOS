#!/usr/bin/env sh
# Compile and run the core module with nothing but the Kotlin compiler.
#
# Gradle ships kotlin-compiler-embeddable and kotlin-stdlib inside its own
# distribution, so the core builds with no Maven access and no Android SDK.
# That is the whole reason the core has no third-party dependencies: it makes
# the protocol testable in an environment where an APK cannot be produced.
set -eu

GRADLE_LIB="${GRADLE_LIB:-/opt/gradle-8.14.3/lib}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${OUT:-$HERE/build/core}"

CP=""
for jar in "$GRADLE_LIB"/kotlin-*.jar "$GRADLE_LIB"/kotlinx-*.jar \
           "$GRADLE_LIB"/trove4j*.jar "$GRADLE_LIB"/annotations-*.jar; do
    [ -f "$jar" ] && CP="$CP:$jar"
done
CP="${CP#:}"
STDLIB="$GRADLE_LIB/kotlin-stdlib-2.0.21.jar"

rm -rf "$OUT"
mkdir -p "$OUT"

echo "Compiling core..."
java -Xmx1g -cp "$CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
    "$HERE/core/src/main/kotlin" -d "$OUT" -no-stdlib -cp "$STDLIB" -nowarn

echo "Running self test${1:+ + conformance}..."
java -cp "$OUT:$STDLIB" casecommand.core.MainKt "$@"

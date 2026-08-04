package casecommand.core

/**
 * Runs the core's own tests, then the twelve conformance rules against a live
 * server. No JUnit — that would be a Maven dependency, and this module is built
 * with nothing but the Kotlin compiler so it can be verified in an environment
 * with no Android SDK and no network.
 *
 *   Main <baseUrl> <pairingCode>
 */
private var failures = 0
private var checks = 0

private fun check(name: String, condition: Boolean, detail: String = "") {
    checks++
    if (condition) {
        println("  PASS  $name${if (detail.isEmpty()) "" else "  — $detail"}")
    } else {
        failures++
        println("  FAIL  $name${if (detail.isEmpty()) "" else "  — $detail"}")
    }
}

private fun <T> expectThrows(name: String, type: Class<*>, block: () -> T) {
    checks++
    try {
        block()
        failures++
        println("  FAIL  $name — expected ${type.simpleName}, nothing was thrown")
    } catch (e: Exception) {
        if (type.isInstance(e)) println("  PASS  $name — ${e.javaClass.simpleName}")
        else { failures++; println("  FAIL  $name — got ${e.javaClass.simpleName}: ${e.message}") }
    }
}

private fun jsonTests() {
    println("\nJSON")
    val parsed = Json.parse("""{"a":1,"b":[true,null,"x"],"c":{"d":-2.5},"e":"line\nbreak"}""")
    check("object field", parsed["a"].asInt() == 1)
    check("array element", parsed["b"][2].asString() == "x")
    check("nested", parsed["c"]["d"].asString() == "-2.5")
    check("escape", parsed["e"].asString() == "line\nbreak")
    check("missing field is null, not a crash", parsed["nope"]["deeper"].asString() == null)
    check("round trip", Json.parse(parsed.write()).write() == parsed.write())
    check("unicode escape", Json.parse("""{"u":"é"}""")["u"].asString() == "é")
    check("quotes survive", Json.parse(jsonOf("q" to "he said \"no\"").write())["q"].asString()
        == "he said \"no\"")
    expectThrows("trailing content refused", IllegalArgumentException::class.java) {
        Json.parse("""{"a":1} extra""")
    }
    // size() counts an object's fields as well as an array's items. Asking
    // asList().size for an object returned 0, and a count reading zero when the
    // truth is ten is the kind of wrong number this system exists to prevent.
    check("size() counts array items", Json.parse("""[1,2,3]""").size() == 3)
    check("size() counts object fields", Json.parse("""{"a":1,"b":2}""").size() == 2)
    check("size() of a scalar is zero", Json.parse("""7""").size() == 0)
}

private fun storeTests() {
    println("\nLocal store")
    val store = MemoryStore()

    val data = "the original exhibit".toByteArray()
    val digest = sha256(data)
    store.putBlob(digest, "CC-DOC-000001", "exhibit.txt", data)
    check("blob round trip", store.blob(digest)!!.contentEquals(data))

    // "It was in my phone's cache" is not a provenance.
    store.tamperWithBlob(digest, "something else entirely".toByteArray())
    expectThrows("tampered cache is refused", CorruptCacheException::class.java) {
        store.blob(digest)
    }
    check("and discarded, not served next time", store.blob(digest) == null)

    val item = Outgoing("abc123", "notice.jpg", "bytes".toByteArray(),
        null, "PHOTO", "2026-08-04T09:00:00.000Z", null)
    store.queue(item)
    store.queue(item)
    check("a replayed queue is one capture", store.pending().size == 1)
    store.markSent("abc123")
    check("sent leaves the outbox", store.pending().isEmpty())
    store.queue(item)
    check("and a sent capture is not re-queued", store.pending().isEmpty())

    // A phone that cannot sync is worse than one that does not know a column.
    store.apply("issues", listOf(Json.parse(
        """{"id":1,"matter_id":2,"updated_at":"2026-01-01","title":"Curtailment","from_the_future":7}""")))
    val row = store.row("issues", 1)
    check("unknown column survives", row["title"].asString() == "Curtailment" &&
        row["from_the_future"].asInt() == 7)
    check("mirror covers every replicated table", MIRROR_TABLES.size == 7)
}

private fun offlineTests() {
    println("\nOffline behaviour")
    val store = MemoryStore()
    store.setMeta("token", "pretend")
    store.setMeta("last_sync_at", "2026-08-04T06:00:00.000Z")
    val client = CaseClient("http://example.invalid", store, DeadTransport())

    val result = client.syncOrOffline()
    check("unreachable is not an error", !result.online)
    check("and it says when it last synced",
        result.lastSyncedAt == "2026-08-04T06:00:00.000Z")

    val uid = client.capture("notice.txt", "bytes".toByteArray(), "2026-08-04T09:00:00.000Z")
    check("a capture with no network is kept", store.pending().any { it.clientUid == uid })
    check("and records why it did not send",
        store.pending().first().lastError?.contains("no route") == true)
}

fun main(args: Array<String>) {
    println("Case Command Android core — self test")
    jsonTests()
    storeTests()
    offlineTests()

    println("\n$checks checks, $failures failure(s)")
    if (args.size >= 2) {
        println("\n" + "=".repeat(64))
        // Revocation happens on the desktop, not through the API — a device
        // must not be able to revoke itself, so there is no endpoint for it.
        // To test the rule end to end the harness runs the desktop command,
        // with {uid} replaced by the paired device. Without it the rule is
        // reported as not run rather than quietly passing.
        val revoke: ((String) -> Unit)? = args.getOrNull(2)?.let { template ->
            { uid: String ->
                val command = template.replace("{uid}", uid).split(" ").filter { it.isNotEmpty() }
                val exit = ProcessBuilder(command).redirectErrorStream(true)
                    .start().let { process ->
                        process.inputStream.readBytes()
                        process.waitFor()
                    }
                if (exit != 0) println("  (revoke command exited $exit)")
            }
        }
        val report = conformance(args[0], args[1], HttpTransport(), revoke)
        print(format(report))
        if (!report.allPassed) failures++
    } else {
        println("\n(pass <baseUrl> <pairingCode> [revokeCommand] to also run the")
        println(" twelve conformance rules; {uid} in the command is replaced by")
        println(" the paired device_uid)")
    }

    if (failures > 0) {
        System.exit(1)
    }
}

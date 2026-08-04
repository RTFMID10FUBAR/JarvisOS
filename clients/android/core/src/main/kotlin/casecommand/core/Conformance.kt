package casecommand.core

/**
 * The twelve rules a Case Command client has to obey.
 *
 * Identical to `CONFORMANCE_RULES` in `case_command/client.py`, deliberately.
 * The Python reference passes all twelve against a live server; this module
 * passes the same twelve, against the same server, driven from Kotlin. If the
 * two ever disagree, one of them is wrong and the disagreement is the finding.
 *
 * Each rule is a failure that has actually happened to somebody's sync client,
 * not a hypothetical. Rule six in particular exists because the first version
 * of it — checking that the server *had* a `more_available` field — proved
 * nothing, and rewriting it to walk the whole record one row at a time found a
 * server bug that was silently dropping 75 of 80 rows.
 */
val CONFORMANCE_RULES: List<Pair<String, String>> = listOf(
    "open-index" to "The index is readable without a token.",
    "auth-required" to "Sync without a token is refused.",
    "pair-once" to "A pairing code works once and not twice.",
    "full-sync" to "A first sync pulls the whole record.",
    "delta-sync" to "A second sync pulls only what changed.",
    "cursor-holds" to "The cursor is not advanced past a truncated page.",
    "blob-verified" to "A cached original is verified against the record's digest.",
    "offline-read" to "A pinned document is readable with the network down.",
    "offline-provenance" to "An offline document still carries its date source.",
    "capture-survives-offline" to "A capture taken offline is kept and sent later.",
    "capture-dedupes" to "A replayed upload is one capture, not two.",
    "revocation-surfaces" to "A revoked device is told, not silently retried.",
)

data class RuleResult(val rule: String, val passed: Boolean, val detail: String)

data class ConformanceReport(val results: List<RuleResult>) {
    val passed: Int get() = results.count { it.passed }
    val total: Int get() = results.size
    val allPassed: Boolean get() = passed == total
}

/**
 * A transport that refuses to connect, for testing the offline path.
 *
 * Simulating "no signal" by pointing at a dead port works, but it depends on
 * nothing listening there, which is not something a test should assume. This
 * makes the failure deliberate.
 */
class DeadTransport : Transport {
    override fun request(
        method: String,
        url: String,
        body: ByteArray?,
        contentType: String?,
        bearer: String?,
    ): Response = throw UnreachableException("no route to host (simulated)")
}

/**
 * Drive a live server through every rule and report pass or fail for each.
 *
 * [revoke] is called with the device_uid to test the revocation rule; pass null
 * to skip it. Everything else runs against the server as a real client would,
 * over HTTP.
 */
fun conformance(
    baseUrl: String,
    code: String,
    transport: Transport = HttpTransport(),
    revoke: ((String) -> Unit)? = null,
): ConformanceReport {
    val results = ArrayList<RuleResult>()
    fun record(rule: String, ok: Boolean, detail: String) {
        results.add(RuleResult(rule, ok, detail))
    }

    val store = MemoryStore()
    val client = CaseClient(baseUrl, store, transport)

    // 1. open index
    try {
        val index = client.index()
        record(
            "open-index", index["api_version"].asString() == "v1",
            "api_version=${index["api_version"].asString()}, " +
                "${index["endpoints"].size()} endpoints"
        )
    } catch (e: Exception) {
        record("open-index", false, e.message ?: "failed")
    }

    // 2. auth required
    try {
        transport.request("GET", "$baseUrl/api/v1/sync").let { response ->
            record("auth-required", response.status == 401, "HTTP ${response.status}")
        }
    } catch (e: Exception) {
        record("auth-required", false, e.message ?: "failed")
    }

    // 3. pairing works once
    val paired = try {
        client.pair(code, "Kotlin conformance")
    } catch (e: Exception) {
        record("pair-once", false, "first pairing failed: ${e.message}")
        return ConformanceReport(fillMissing(results))
    }
    try {
        CaseClient(baseUrl, MemoryStore(), transport).pair(code, "Replay")
        record("pair-once", false, "the same code paired a second device")
    } catch (e: ClientException) {
        record("pair-once", e.status in listOf(400, 404, 409), "refused: ${e.message}")
    }

    // 4 & 5. full then delta
    val first = client.sync(full = true)
    record("full-sync", first.total > 0, "${first.total} rows in ${first.rounds} round(s)")

    val second = client.sync()
    record("delta-sync", second.total == 0, "${second.total} rows changed since the first sync")

    // 6. the cursor must not run past a truncated page. Force truncation with a
    // deliberately tiny page and check the client both looped and ended up
    // holding exactly what one large page held.
    val expected = MIRROR_TABLES.associateWith { store.count(it) }
    val pagedStore = MemoryStore()
    pagedStore.setMeta("token", store.meta("token"))
    val walked = CaseClient(baseUrl, pagedStore, transport).sync(full = true, pageSize = 1)
    val got = MIRROR_TABLES.associateWith { pagedStore.count(it) }
    record(
        "cursor-holds",
        walked.paged && walked.rounds > 1 && got == expected,
        "${walked.rounds} rounds at 1 row/table/page -> ${got.values.sum()} rows, " +
            "same as the ${expected.values.sum()} from one large page"
    )

    // 7-9. a pinned original, read back offline, with its provenance intact
    val doc = store.rows("documents").firstOrNull { it["sha256"].asString() != null }
    if (doc == null) {
        for (rule in listOf("blob-verified", "offline-read", "offline-provenance")) {
            record(rule, false, "no documents with a digest were synced")
        }
    } else {
        val uid = doc["doc_uid"].asString()!!
        val sha = doc["sha256"].asString()!!
        try {
            val size = client.pin(uid, sha, doc["original_filename"].asString() ?: uid)
            record("blob-verified", store.blob(sha) != null, "$size bytes cached and re-verified")
        } catch (e: Exception) {
            record("blob-verified", false, e.message ?: "failed")
        }
        val offline = client.readOffline(uid)
        record("offline-read", offline.originalAvailableOffline,
            "$uid readable from the device's own copy")
        record("offline-provenance", !offline.dateSource.isNullOrBlank(),
            "date_source=${offline.dateSource}")
    }

    // 10. a capture taken with no network is kept and sent on reconnect
    val offlineClient = CaseClient(baseUrl, store, DeadTransport())
    val clientUid = offlineClient.capture(
        filename = "notice.txt",
        data = "posted notice, photographed at the courthouse".toByteArray(),
        capturedAt = "2026-08-04T09:00:00.000Z",
        note = "kotlin conformance",
    )
    val heldWhileOffline = store.pending().any { it.clientUid == clientUid }
    val sent = client.flush()
    record(
        "capture-survives-offline",
        heldWhileOffline && clientUid in sent,
        "queued while unreachable, sent on reconnect (${sent.size} item(s))"
    )

    // 11. a replayed upload is one capture, not two
    try {
        val replay = Outgoing(
            clientUid, "notice.txt",
            "posted notice, photographed at the courthouse".toByteArray(),
            null, "PHOTO", "2026-08-04T09:00:00.000Z", "kotlin conformance",
        )
        val again = client.upload(replay)
        record("capture-dedupes", again["duplicate"].asBool(),
            "server answered duplicate=${again["duplicate"].asBool()}")
    } catch (e: Exception) {
        record("capture-dedupes", false, e.message ?: "failed")
    }

    // 12. revocation is surfaced, never silently retried
    val deviceUid = paired["device_uid"].asString()
    if (revoke != null && deviceUid != null) {
        revoke(deviceUid)
        try {
            client.sync()
            record("revocation-surfaces", false, "sync still worked after revocation")
        } catch (e: RevokedException) {
            record("revocation-surfaces", true, "HTTP ${e.status}: ${e.message}")
        } catch (e: ClientException) {
            record("revocation-surfaces", false, "wrong error type: ${e.message}")
        }
    } else {
        record("revocation-surfaces", false, "not tested (no revoke callback)")
    }

    return ConformanceReport(fillMissing(results))
}

private fun fillMissing(results: MutableList<RuleResult>): List<RuleResult> {
    val covered = results.map { it.rule }.toSet()
    for ((rule, _) in CONFORMANCE_RULES) {
        if (rule !in covered) results.add(RuleResult(rule, false, "not run"))
    }
    return results
}

fun format(report: ConformanceReport): String {
    val descriptions = CONFORMANCE_RULES.toMap()
    val width = report.results.maxOf { it.rule.length }
    val out = StringBuilder("Client conformance: ${report.passed}/${report.total} rules\n\n")
    for (result in report.results) {
        val mark = if (result.passed) "PASS" else "FAIL"
        out.append("  [$mark] ${result.rule.padEnd(width)}  ${result.detail}\n")
        out.append("         ${" ".repeat(width)}  ${descriptions[result.rule] ?: ""}\n")
    }
    if (!report.allPassed) {
        out.append("\nA client that does not pass all of these can lose a document\n")
        out.append("without saying so. Do not ship it.\n")
    }
    return out.toString()
}

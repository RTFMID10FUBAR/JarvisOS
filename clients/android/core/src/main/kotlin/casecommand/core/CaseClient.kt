package casecommand.core

import java.net.URLEncoder
import java.util.UUID

/** Tables the server replicates. */
val MIRROR_TABLES = listOf(
    "matters", "documents", "issues", "deadlines", "events",
    "preservation_items", "access_barriers",
)

/** Rows per table per request. Smaller than the server's cap on purpose. */
const val SYNC_PAGE = 500

/** A server that keeps saying "more" must not spin a phone's battery flat. */
const val MAX_SYNC_ROUNDS = 100

data class SyncResult(
    val rounds: Int,
    val applied: Map<String, Int>,
    val total: Int,
    val cursor: String?,
    val fullSync: Boolean,
    val paged: Boolean,
    val unknownTables: List<String>,
    val online: Boolean = true,
    val offlineReason: String? = null,
    val lastSyncedAt: String? = null,
)

data class OfflineDocument(
    val docUid: String,
    val title: String?,
    val documentDate: String?,
    /** How the date was read — the signature block, a dated line, a service date. */
    val dateSource: String?,
    val extractLine: String?,
    val extractLocator: String?,
    val verificationStatus: String?,
    val originalAvailableOffline: Boolean,
    val byteSize: Int?,
)

data class PinResult(
    val cached: List<String>,
    val skipped: List<Pair<String, String>>,
    val failed: List<Pair<String, String>>,
    val bytesHeld: Long,
)

/**
 * The phone side of the Case Command protocol.
 *
 * This is a port of `case_command/client.py`, and deliberately a close one. The
 * Python reference passes twelve conformance rules against a live server; this
 * passes the same twelve, driven by the same harness. Where the two differ in
 * behaviour, one of them is wrong.
 *
 * Read-only against the case, with one exception: evidence captured on the
 * device is uploaded. It cannot edit a fact, mark anything verified, or file
 * anything. Those limits are enforced on the server too — this is a client, and
 * a client's promises are not security.
 */
class CaseClient(
    baseUrl: String,
    private val store: RecordStore,
    private val transport: Transport = HttpTransport(),
) {
    private val base = baseUrl.trimEnd('/')

    val token: String? get() = store.meta("token")
    val cursor: String? get() = store.meta("sync_cursor")

    // -- plumbing -----------------------------------------------------------
    private fun call(
        method: String,
        path: String,
        body: ByteArray? = null,
        contentType: String? = null,
        auth: Boolean = true,
    ): Response {
        val bearer = if (auth) (token ?: throw ClientException("this device is not paired yet")) else null
        val response = transport.request(method, "$base/api/v1$path", body, contentType, bearer)
        if (response.status in 200..299) return response

        val detail = runCatching { response.json()["error"].asString() }.getOrNull()
            ?: response.text().take(200)
        throw when (response.status) {
            403 -> RevokedException(detail)
            else -> ClientException(detail, response.status)
        }
    }

    // -- pairing ------------------------------------------------------------
    /** Redeem a code shown on the desktop. The token is stored locally, once. */
    fun pair(code: String, label: String, platform: String = "android", appVersion: String? = null): Json {
        val payload = jsonOf(
            "code" to code.trim().uppercase(),
            "label" to label,
            "platform" to platform,
            "app_version" to appVersion,
        ).write().toByteArray(Charsets.UTF_8)

        val result = call("POST", "/pair", payload, "application/json", auth = false).json()
        store.setMeta("token", result["token"].asString())
        store.setMeta("device_uid", result["device_uid"].asString())
        store.setMeta("server", base)
        return result
    }

    fun index(): Json = call("GET", "/", auth = false).json()

    // -- sync ---------------------------------------------------------------
    /**
     * Pull everything that changed, looping until the server stops saying there is more.
     *
     * The cursor is only saved once the server reports nothing further is
     * waiting. A client that saves the cursor after a truncated page believes
     * it is current while rows it has never seen sit on the other side — and it
     * will never ask for them again, because as far as it knows it already has
     * them. That is how a sync client loses a document silently, and it is the
     * one failure this system cannot tolerate.
     */
    fun sync(full: Boolean = false, pageSize: Int = SYNC_PAGE): SyncResult {
        val since = if (full) null else cursor
        val applied = MIRROR_TABLES.associateWith { 0 }.toMutableMap()
        var current = since
        var rounds = 0
        var paged = false
        var lastCounts: Map<String, Json> = emptyMap()

        while (true) {
            rounds++
            if (rounds > MAX_SYNC_ROUNDS) {
                throw ClientException(
                    "sync did not converge after $MAX_SYNC_ROUNDS rounds; " +
                        "the server keeps reporting more changes"
                )
            }

            val query = buildString {
                append("?limit=").append(pageSize)
                current?.let { append("&since=").append(URLEncoder.encode(it, "UTF-8")) }
            }
            val page = call("GET", "/sync$query").json()

            for ((table, rows) in page["changed"].asMap()) {
                // A newer server may send a table this build does not know.
                // Skipping it keeps the phone useful; it is reported below.
                if (table !in MIRROR_TABLES) continue
                applied[table] = (applied[table] ?: 0) + store.apply(table, rows.asList())
            }

            current = page["next_cursor"].asString()
            lastCounts = page["counts"].asMap()
            if (!page["more_available"].asBool()) break
            // More is waiting. The cursor stays out of the store until the
            // server says it is finished, so a crash mid-loop resumes from the
            // last complete position rather than skipping the remainder.
            paged = true
        }

        store.setMeta("sync_cursor", current)
        store.setMeta("last_sync_at", current)

        return SyncResult(
            rounds = rounds,
            applied = applied,
            total = applied.values.sum(),
            cursor = current,
            fullSync = since == null,
            paged = paged,
            unknownTables = (lastCounts.keys - MIRROR_TABLES.toSet()).sorted(),
        )
    }

    /**
     * Sync if the network is there; otherwise say so and carry on.
     *
     * This is the call a screen should make. Being offline is a normal state
     * for this system, not an error condition.
     */
    fun syncOrOffline(): SyncResult = try {
        sync()
    } catch (e: UnreachableException) {
        SyncResult(
            rounds = 0,
            applied = MIRROR_TABLES.associateWith { 0 },
            total = 0,
            cursor = cursor,
            fullSync = false,
            paged = false,
            unknownTables = emptyList(),
            online = false,
            offlineReason = e.message,
            lastSyncedAt = store.meta("last_sync_at"),
        )
    }

    // -- documents ----------------------------------------------------------
    fun document(docUid: String): Json =
        call("GET", "/documents/${URLEncoder.encode(docUid, "UTF-8")}").json()

    /**
     * Download an original and keep it, verified against the record's digest.
     *
     * If the bytes that arrive do not hash to what the record says they should,
     * nothing is cached. A wrong exhibit at a hearing is worse than a missing
     * one, because a missing one is obvious.
     */
    fun pin(docUid: String, sha256: String, filename: String): Int {
        val bytes = call("GET", "/documents/${URLEncoder.encode(docUid, "UTF-8")}/original").body
        val digest = sha256(bytes)
        if (digest != sha256) {
            throw ClientException(
                "$docUid: downloaded bytes hash to ${digest.take(12)} but the record " +
                    "says ${sha256.take(12)}; nothing was cached"
            )
        }
        store.putBlob(sha256, docUid, filename, bytes)
        return bytes.size
    }

    /**
     * Cache the originals for a matter.
     *
     * Reports exactly what it skipped. A pack that silently drops documents is
     * the failure mode this whole system exists to prevent.
     */
    fun pinMatter(matterId: Long, budgetBytes: Long? = null): PinResult {
        val cached = ArrayList<String>()
        val skipped = ArrayList<Pair<String, String>>()
        val failed = ArrayList<Pair<String, String>>()
        var used = store.cachedBytes()

        for (doc in store.rows("documents", matterId)) {
            val sha = doc["sha256"].asString()
            val uid = doc["doc_uid"].asString()
            if (sha == null || uid == null) {
                skipped.add((uid ?: "?") to "no digest recorded")
                continue
            }
            if (runCatching { store.blob(sha) }.getOrNull() != null) continue

            val size = (doc["byte_size"].asLong() ?: 0L)
            if (budgetBytes != null && used + size > budgetBytes) {
                skipped.add(uid to "over the storage budget")
                continue
            }
            try {
                used += pin(uid, sha, doc["original_filename"].asString() ?: uid)
                cached.add(uid)
            } catch (e: ClientException) {
                failed.add(uid to (e.message ?: "unknown failure"))
            }
        }
        return PinResult(cached, skipped, failed, store.cachedBytes())
    }

    /** A document as the device can show it with no network at all. */
    fun readOffline(docUid: String): OfflineDocument {
        val doc = store.rows("documents").firstOrNull { it["doc_uid"].asString() == docUid }
            ?: throw ClientException("$docUid is not in this device's copy", 404)
        val sha = doc["sha256"].asString()
        val bytes = if (sha != null) runCatching { store.blob(sha) }.getOrNull() else null

        return OfflineDocument(
            docUid = docUid,
            title = doc["title"].asString(),
            documentDate = doc["document_date"].asString(),
            // Provenance travels with the document. On a phone, in a hallway,
            // under time pressure, this is exactly when a date's source matters.
            dateSource = doc["date_source"].asString(),
            extractLine = doc["extract_line"].asString(),
            extractLocator = doc["extract_locator"].asString(),
            verificationStatus = doc["verification_status"].asString(),
            originalAvailableOffline = bytes != null,
            byteSize = bytes?.size,
        )
    }

    // -- captures -----------------------------------------------------------
    /**
     * Queue evidence captured on the device, then try to send it.
     *
     * Queued first and sent second, always. A photo of a posted notice taken in
     * a building with no signal has to survive the walk back to the car.
     */
    fun capture(
        filename: String,
        data: ByteArray,
        capturedAt: String,
        matterId: Long? = null,
        kind: String = "PHOTO",
        note: String? = null,
    ): String {
        val clientUid = UUID.randomUUID().toString().replace("-", "")
        store.queue(Outgoing(clientUid, filename, data, matterId, kind, capturedAt, note))
        flush()
        return clientUid
    }

    /** Send everything waiting in the outbox. Safe to call at any time. */
    fun flush(): List<String> {
        val sent = ArrayList<String>()
        for (item in store.pending()) {
            try {
                upload(item)
                store.markSent(item.clientUid)
                sent.add(item.clientUid)
            } catch (e: ClientException) {
                store.markFailed(item.clientUid, e.message ?: "unknown failure")
            }
        }
        return sent
    }

    internal fun upload(item: Outgoing): Json {
        val fields = LinkedHashMap<String, String>()
        fields["client_uid"] = item.clientUid
        fields["capture_kind"] = item.kind
        fields["captured_at"] = item.capturedAt
        item.matterId?.let { fields["matter_id"] = it.toString() }
        item.note?.let { fields["device_note"] = it }

        val (body, contentType) = multipart(fields, item.filename, item.data)
        return call("POST", "/captures", body, contentType).json()
    }

    fun pendingCount(): Int = store.pending().size
}

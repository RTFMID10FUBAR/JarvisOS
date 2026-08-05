package casecommand.core

import java.security.MessageDigest

/** SHA-256 of some bytes, lowercase hex. Available on both the JVM and Android. */
fun sha256(data: ByteArray): String =
    MessageDigest.getInstance("SHA-256").digest(data)
        .joinToString("") { "%02x".format(it) }

/** What this device holds. */
data class Record(
    val table: String,
    val id: Long,
    val matterId: Long?,
    val updatedAt: String?,
    val payload: Json,
)

/** A capture waiting to be uploaded. */
data class Outgoing(
    val clientUid: String,
    val filename: String,
    val data: ByteArray,
    val matterId: Long?,
    val kind: String,
    val capturedAt: String,
    val note: String?,
    var attempts: Int = 0,
    var lastError: String? = null,
) {
    // Data classes with a ByteArray need these written out; the generated ones
    // compare by reference, which would make two identical captures look
    // different and one retried capture look like two.
    override fun equals(other: Any?): Boolean =
        other is Outgoing && clientUid == other.clientUid

    override fun hashCode(): Int = clientUid.hashCode()
}

/**
 * The device's own copy of the record.
 *
 * An interface rather than a class, for one concrete reason: Android's SQLite
 * lives behind `android.database`, which cannot be loaded on a plain JVM. If
 * the sync engine talked to SQLite directly, none of it could be tested without
 * an emulator — and in an environment with no Android SDK, that means not
 * tested at all. Behind this interface the whole protocol runs and is verified
 * on the JVM, and the Android side supplies storage and nothing else.
 */
interface RecordStore {
    // -- small persistent values: the token, the sync cursor, last sync time --
    fun meta(key: String): String?
    fun setMeta(key: String, value: String?)

    // -- synced rows -------------------------------------------------------
    /** Upsert by (table, id). Returns how many rows were written. */
    fun apply(table: String, rows: List<Json>): Int
    fun rows(table: String, matterId: Long? = null): List<Json>
    fun row(table: String, id: Long): Json?
    fun count(table: String): Int

    // -- cached original bytes, keyed by the record's own digest -----------
    fun putBlob(sha256: String, docUid: String, filename: String, data: ByteArray)
    /**
     * Cached bytes, or null.
     *
     * Implementations must recompute the digest on the way out and discard a
     * mismatch. A cache that can hand back the wrong bytes is worse than no
     * cache: this record has to be quotable in a hearing, and "it was in my
     * phone's cache" is not a provenance.
     */
    fun blob(sha256: String): ByteArray?
    fun cachedBytes(): Long

    // -- the outbox --------------------------------------------------------
    fun queue(item: Outgoing)
    fun pending(): List<Outgoing>
    fun markSent(clientUid: String)
    fun markFailed(clientUid: String, error: String)
}

/** Thrown when a cached blob does not match the digest it is filed under. */
class CorruptCacheException(val sha256: String) :
    Exception("cached copy of ${sha256.take(12)} does not match its digest; it was discarded")

/**
 * An in-memory store.
 *
 * This is what the conformance run and the unit tests use. It is not a toy
 * stand-in — it implements every rule the interface states, including
 * discarding a blob whose digest no longer matches, so a bug in the sync engine
 * shows up here rather than waiting for a device.
 */
class MemoryStore : RecordStore {
    private val meta = HashMap<String, String>()
    private val records = LinkedHashMap<Pair<String, Long>, Record>()
    private val blobs = HashMap<String, ByteArray>()
    private val outbox = LinkedHashMap<String, Outgoing>()
    private val sent = HashSet<String>()

    override fun meta(key: String): String? = meta[key]

    override fun setMeta(key: String, value: String?) {
        if (value == null) meta.remove(key) else meta[key] = value
    }

    override fun apply(table: String, rows: List<Json>): Int {
        var written = 0
        for (row in rows) {
            val id = row["id"].asLong() ?: continue
            records[table to id] = Record(
                table = table,
                id = id,
                matterId = row["matter_id"].asLong(),
                updatedAt = row["updated_at"].asString(),
                payload = row,
            )
            written++
        }
        return written
    }

    override fun rows(table: String, matterId: Long?): List<Json> =
        records.values
            .filter { it.table == table && (matterId == null || it.matterId == matterId) }
            .sortedBy { it.id }
            .map { it.payload }

    override fun row(table: String, id: Long): Json? = records[table to id]?.payload

    override fun count(table: String): Int = records.keys.count { it.first == table }

    override fun putBlob(sha256: String, docUid: String, filename: String, data: ByteArray) {
        blobs[sha256] = data
    }

    override fun blob(sha256: String): ByteArray? {
        val data = blobs[sha256] ?: return null
        if (sha256(data) != sha256) {
            blobs.remove(sha256)
            throw CorruptCacheException(sha256)
        }
        return data
    }

    override fun cachedBytes(): Long = blobs.values.sumOf { it.size.toLong() }

    override fun queue(item: Outgoing) {
        // The client_uid is generated once on the device and reused on every
        // retry, so a dropped upload stays one capture.
        if (outbox.containsKey(item.clientUid) || item.clientUid in sent) return
        outbox[item.clientUid] = item
    }

    override fun pending(): List<Outgoing> = outbox.values.toList()

    override fun markSent(clientUid: String) {
        outbox.remove(clientUid)
        sent.add(clientUid)
    }

    override fun markFailed(clientUid: String, error: String) {
        outbox[clientUid]?.let { it.attempts += 1; it.lastError = error }
    }

    /** Test hook: corrupt a cached blob without going through putBlob. */
    fun tamperWithBlob(sha256: String, replacement: ByteArray) {
        blobs[sha256] = replacement
    }
}

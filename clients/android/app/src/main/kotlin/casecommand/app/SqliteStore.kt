package casecommand.app

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import casecommand.core.CorruptCacheException
import casecommand.core.Json
import casecommand.core.Outgoing
import casecommand.core.RecordStore
import casecommand.core.asLong
import casecommand.core.asString
import casecommand.core.get
import casecommand.core.sha256
import casecommand.core.write

/**
 * The device's copy, on SQLite.
 *
 * NOT COMPILED IN CI. This file imports `android.database`, which cannot be
 * loaded on a plain JVM, so it is the one part of the storage layer that the
 * conformance run here cannot exercise. Everything it is required to do is
 * stated by `RecordStore` in the core module, and the core's `MemoryStore`
 * implements the same contract and is fully tested — so what is untested here
 * is the SQL, not the protocol.
 *
 * The schema mirrors `MIRROR_SCHEMA` in `case_command/client.py` deliberately.
 * Three tables carry the whole thing: what was synced, what was cached, and
 * what is waiting to go out.
 */
class SqliteStore(context: Context) : RecordStore {

    private val helper = object : SQLiteOpenHelper(context, "case_command.db", null, 1) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")

            // Rows are stored as JSON rather than as seven mirrored schemas so
            // the server's columns can grow without the phone needing a
            // migration to keep working. A phone that cannot sync is worse than
            // a phone that does not know about a new column.
            db.execSQL(
                """
                CREATE TABLE records (
                    table_name TEXT NOT NULL,
                    row_id     INTEGER NOT NULL,
                    matter_id  INTEGER,
                    updated_at TEXT,
                    payload    TEXT NOT NULL,
                    PRIMARY KEY (table_name, row_id)
                )
                """.trimIndent()
            )
            db.execSQL("CREATE INDEX idx_records_matter ON records(table_name, matter_id)")

            // Keyed by content, so a corrupted or substituted file cannot
            // masquerade as the original.
            db.execSQL(
                """
                CREATE TABLE blobs (
                    sha256    TEXT PRIMARY KEY,
                    doc_uid   TEXT,
                    filename  TEXT,
                    byte_size INTEGER NOT NULL,
                    data      BLOB NOT NULL,
                    cached_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """.trimIndent()
            )

            // client_uid is generated once on the device and reused on every
            // retry, so a dropped upload becomes one capture rather than two.
            db.execSQL(
                """
                CREATE TABLE outbox (
                    client_uid  TEXT PRIMARY KEY,
                    filename    TEXT NOT NULL,
                    data        BLOB NOT NULL,
                    matter_id   INTEGER,
                    kind        TEXT NOT NULL DEFAULT 'PHOTO',
                    captured_at TEXT NOT NULL,
                    note        TEXT,
                    state       TEXT NOT NULL DEFAULT 'PENDING',
                    attempts    INTEGER NOT NULL DEFAULT 0,
                    last_error  TEXT,
                    queued_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """.trimIndent()
            )
        }

        override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) {
            // Nothing to migrate yet. When there is, it migrates — it does not
            // drop and refetch. A phone that discards its copy on upgrade is a
            // phone with no record on the morning of a hearing.
        }
    }

    private val db: SQLiteDatabase get() = helper.writableDatabase

    // -- meta ---------------------------------------------------------------
    override fun meta(key: String): String? =
        db.rawQuery("SELECT value FROM meta WHERE key=?", arrayOf(key)).use {
            if (it.moveToFirst()) it.getString(0) else null
        }

    override fun setMeta(key: String, value: String?) {
        if (value == null) {
            db.delete("meta", "key=?", arrayOf(key))
        } else {
            db.insertWithOnConflict(
                "meta", null,
                ContentValues().apply { put("key", key); put("value", value) },
                SQLiteDatabase.CONFLICT_REPLACE
            )
        }
    }

    // -- records ------------------------------------------------------------
    override fun apply(table: String, rows: List<Json>): Int {
        var written = 0
        db.beginTransaction()
        try {
            for (row in rows) {
                val id = row["id"].asLong() ?: continue
                db.insertWithOnConflict(
                    "records", null,
                    ContentValues().apply {
                        put("table_name", table)
                        put("row_id", id)
                        row["matter_id"].asLong()?.let { put("matter_id", it) }
                        put("updated_at", row["updated_at"].asString())
                        put("payload", row.write())
                    },
                    SQLiteDatabase.CONFLICT_REPLACE
                )
                written++
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return written
    }

    override fun rows(table: String, matterId: Long?): List<Json> {
        val (where, args) =
            if (matterId == null) "table_name=?" to arrayOf(table)
            else "table_name=? AND matter_id=?" to arrayOf(table, matterId.toString())
        return db.query("records", arrayOf("payload"), where, args, null, null, "row_id")
            .use { cursor ->
                buildList {
                    while (cursor.moveToNext()) add(Json.parse(cursor.getString(0)))
                }
            }
    }

    override fun row(table: String, id: Long): Json? =
        db.query(
            "records", arrayOf("payload"), "table_name=? AND row_id=?",
            arrayOf(table, id.toString()), null, null, null
        ).use { if (it.moveToFirst()) Json.parse(it.getString(0)) else null }

    override fun count(table: String): Int =
        db.rawQuery("SELECT COUNT(*) FROM records WHERE table_name=?", arrayOf(table))
            .use { if (it.moveToFirst()) it.getInt(0) else 0 }

    // -- blobs --------------------------------------------------------------
    override fun putBlob(sha256: String, docUid: String, filename: String, data: ByteArray) {
        db.insertWithOnConflict(
            "blobs", null,
            ContentValues().apply {
                put("sha256", sha256)
                put("doc_uid", docUid)
                put("filename", filename)
                put("byte_size", data.size)
                put("data", data)
            },
            SQLiteDatabase.CONFLICT_REPLACE
        )
    }

    override fun blob(sha256: String): ByteArray? {
        val data = db.query("blobs", arrayOf("data"), "sha256=?", arrayOf(sha256), null, null, null)
            .use { if (it.moveToFirst()) it.getBlob(0) else null } ?: return null

        // Recomputed on the way out. A cache that can hand back the wrong bytes
        // is worse than no cache: this record has to be quotable in a hearing,
        // and "it was in my phone's cache" is not a provenance.
        if (sha256(data) != sha256) {
            db.delete("blobs", "sha256=?", arrayOf(sha256))
            throw CorruptCacheException(sha256)
        }
        return data
    }

    override fun cachedBytes(): Long =
        db.rawQuery("SELECT COALESCE(SUM(byte_size), 0) FROM blobs", null)
            .use { if (it.moveToFirst()) it.getLong(0) else 0L }

    // -- outbox -------------------------------------------------------------
    override fun queue(item: Outgoing) {
        // CONFLICT_IGNORE, not REPLACE: a re-queued capture must not reset the
        // attempt count or resurrect one already sent.
        db.insertWithOnConflict(
            "outbox", null,
            ContentValues().apply {
                put("client_uid", item.clientUid)
                put("filename", item.filename)
                put("data", item.data)
                item.matterId?.let { put("matter_id", it) }
                put("kind", item.kind)
                put("captured_at", item.capturedAt)
                put("note", item.note)
            },
            SQLiteDatabase.CONFLICT_IGNORE
        )
    }

    override fun pending(): List<Outgoing> =
        db.query(
            "outbox", null, "state='PENDING'", null, null, null, "queued_at"
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) {
                    fun str(name: String): String? =
                        cursor.getColumnIndex(name).takeIf { it >= 0 }
                            ?.let { if (cursor.isNull(it)) null else cursor.getString(it) }
                    add(
                        Outgoing(
                            clientUid = str("client_uid")!!,
                            filename = str("filename")!!,
                            data = cursor.getBlob(cursor.getColumnIndexOrThrow("data")),
                            matterId = str("matter_id")?.toLongOrNull(),
                            kind = str("kind") ?: "PHOTO",
                            capturedAt = str("captured_at")!!,
                            note = str("note"),
                            attempts = str("attempts")?.toIntOrNull() ?: 0,
                            lastError = str("last_error"),
                        )
                    )
                }
            }
        }

    override fun markSent(clientUid: String) {
        // The row stays. What this device sent, and when, is worth keeping.
        db.execSQL(
            "UPDATE outbox SET state='SENT', last_error=NULL WHERE client_uid=?",
            arrayOf(clientUid)
        )
    }

    override fun markFailed(clientUid: String, error: String) {
        db.execSQL(
            "UPDATE outbox SET attempts=attempts+1, last_error=? WHERE client_uid=?",
            arrayOf(error, clientUid)
        )
    }
}

package casecommand.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import casecommand.core.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * NOT COMPILED IN CI. This file needs the Android SDK and the Compose compiler
 * plugin, neither of which is available in the build environment used to verify
 * the core. Every screen here is a thin layer over `CaseClient`, which *is*
 * compiled and passes all twelve conformance rules against a live server — so
 * what is unverified here is the layout, not the protocol.
 *
 * Build it with `./gradlew :app:assembleDebug` on a machine with the SDK.
 *
 * The design language matches the desktop: dark operations console, provenance
 * travelling with every date, counts rather than scores, and no affordance that
 * files or serves anything.
 */

private val Ink = Color(0xFF0B111C)
private val Panel = Color(0xFF101725)
private val Line = Color(0xFF1E2A3D)
private val Text = Color(0xFFE6EDF7)
private val Dim = Color(0xFF8A9AB2)
private val Accent = Color(0xFF6EA8FE)
private val Good = Color(0xFF4A9D6B)
private val Warn = Color(0xFFD9A441)
private val Stop = Color(0xFFC9524D)

class MainActivity : ComponentActivity() {
    private lateinit var store: SqliteStore
    private lateinit var client: CaseClient

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = SqliteStore(applicationContext)
        // The server address is entered once at pairing and kept. There is no
        // cloud to fall back to and no default host: this app talks to one
        // machine, the one holding the record.
        client = CaseClient(store.meta("server") ?: "", store)

        setContent {
            MaterialTheme(colorScheme = darkColorScheme(background = Ink, surface = Panel)) {
                if (store.meta("token") == null) {
                    PairScreen(store, pairingLink(intent)) { recreate() }
                } else {
                    HomeScreen(client, store)
                }
            }
        }
    }

    /** A pairing link that was tapped, if this launch came from one. */
    private fun pairingLink(intent: android.content.Intent?): Pair<String, String>? {
        val uri = intent?.data ?: return null
        if (uri.scheme != "casecommand" || uri.host != "pair") return null
        val host = uri.getQueryParameter("host")?.trim().orEmpty()
        val code = uri.getQueryParameter("code")?.trim()?.uppercase().orEmpty()
        return if (host.isNotBlank() && code.isNotBlank()) host to code else null
    }
}

// ---------------------------------------------------------------------------
/**
 * Pairing, with nothing to type.
 *
 * There is no code field and no address field, on purpose. A six-character
 * code read off one screen and typed into another is the worst part of setting
 * this up, and an address field without a code field pairs nothing — so both
 * are gone and the link carries both values instead.
 *
 * The trade this makes: pairing now requires the phone to be able to open the
 * desktop's /pair page in its own browser. That is the same requirement as
 * pairing at all — the app has to reach that server afterwards regardless — so
 * it rules out no case that would otherwise have worked. What it does rule out
 * is pairing from a code somebody read to you over the phone.
 */
@Composable
private fun PairScreen(
    store: SqliteStore,
    fromLink: Pair<String, String>? = null,
    onPaired: () -> Unit,
) {
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    // Arriving from a link is the whole gesture: opening the app *is* pressing
    // the button, so there is no second press. Keyed on the link, so a fresh
    // tap after a failure tries again and a recomposition does not.
    LaunchedEffect(fromLink) {
        val (host, code) = fromLink ?: return@LaunchedEffect
        busy = true; error = null
        val outcome = withContext(Dispatchers.IO) {
            runCatching { CaseClient(host, store).pair(code, android.os.Build.MODEL ?: "Phone") }
        }
        busy = false
        outcome.fold(
            onSuccess = { store.setMeta("server", host); onPaired() },
            onFailure = { error = it.message },
        )
    }

    Column(
        Modifier.fillMaxSize().background(Ink).padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Case Command", color = Text, fontSize = 26.sp, fontWeight = FontWeight.Bold)
        Text("LITIGATION RECORD", color = Dim, fontSize = 11.sp, letterSpacing = 2.sp)
        Spacer(Modifier.height(28.dp))

        when {
            busy -> {
                Text("Pairing with ${fromLink?.first.orEmpty()}", color = Text, fontSize = 15.sp)
                Spacer(Modifier.height(16.dp))
                LinearProgressIndicator(Modifier.fillMaxWidth())
            }

            error != null -> {
                Text("That link did not pair.", color = Stop, fontSize = 15.sp,
                     fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(12.dp))
                Card(Modifier.fillMaxWidth(),
                     colors = CardDefaults.cardColors(containerColor = Panel)) {
                    Text(error.orEmpty(), color = Stop, fontSize = 13.sp,
                         modifier = Modifier.padding(12.dp))
                }
                Spacer(Modifier.height(16.dp))
                // A code is single use and expires in ten minutes, so a second
                // attempt needs a second code — retrying this one would fail
                // the same way and look like the app is broken.
                Text(
                    "Go back to the Pair a device page, press the button again " +
                        "for a new code, and tap the new link. A code works once " +
                        "and expires after ten minutes.",
                    color = Dim, fontSize = 13.sp, lineHeight = 19.sp,
                )
            }

            else -> {
                Text("Pair by tapping a link", color = Text, fontSize = 15.sp,
                     fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(14.dp))
                Text(
                    "On the desktop, open Case Command and choose Pair a device. " +
                        "Open that same page on this phone and tap the link on it. " +
                        "The app opens already paired — there is no code to type " +
                        "and no address to enter.",
                    color = Dim, fontSize = 13.sp, lineHeight = 19.sp,
                )
                Spacer(Modifier.height(14.dp))
                Text(
                    "Both devices have to be on the same network.",
                    color = Dim, fontSize = 13.sp, lineHeight = 19.sp,
                )
            }
        }

        Spacer(Modifier.height(24.dp))
        Text(
            "The token this device receives is shown to it once and stored on " +
                "the desktop only as a hash, so a copied database yields no " +
                "working credential.",
            color = Dim, fontSize = 11.sp, lineHeight = 16.sp,
        )
    }
}

// ---------------------------------------------------------------------------
@Composable
private fun HomeScreen(client: CaseClient, store: SqliteStore) {
    var status by remember { mutableStateOf<SyncResult?>(null) }
    var syncing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun refresh() {
        syncing = true
        scope.launch {
            status = withContext(Dispatchers.IO) { client.syncOrOffline() }
            syncing = false
        }
    }
    LaunchedEffect(Unit) { refresh() }

    val documents = remember(status) { store.rows("documents") }
    val deadlines = remember(status) { store.rows("deadlines") }
    val pending = remember(status) { store.pending().size }

    Column(Modifier.fillMaxSize().background(Ink)) {
        // -- status band ----------------------------------------------------
        // Being offline is a normal state for this system, not an error. The
        // band says which copy is on screen and when it was last reconciled,
        // because a stale record that looks live is the dangerous case.
        Column(Modifier.fillMaxWidth().background(Panel).padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Case Command", color = Text, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.weight(1f))
                TextButton(onClick = { refresh() }, enabled = !syncing) {
                    Text(if (syncing) "Syncing…" else "Sync", color = Accent, fontSize = 13.sp)
                }
            }
            val online = status?.online ?: true
            Text(
                when {
                    status == null -> "Opening this device's copy…"
                    !online -> "Offline. Showing the copy held on this device, " +
                        "last synced ${status?.lastSyncedAt?.take(16) ?: "never"}."
                    else -> "Synced. ${documents.size} document(s) held on this device."
                },
                color = if (online) Dim else Warn, fontSize = 12.sp, lineHeight = 17.sp,
            )
            if (pending > 0) {
                Text(
                    "$pending capture(s) waiting to upload. They are kept on this " +
                        "device until there is a connection.",
                    color = Warn, fontSize = 12.sp,
                )
            }
        }

        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp)) {
            item {
                SectionLabel("Deadlines in the record")
                if (deadlines.isEmpty()) {
                    Honest(
                        "No deadline is recorded for any matter on this device. " +
                            "That is a statement about the record, not a statement " +
                            "that nothing is due."
                    )
                }
            }
            items(deadlines) { DeadlineCard(it) }

            item {
                Spacer(Modifier.height(20.dp))
                SectionLabel("Documents")
                if (documents.isEmpty()) Honest("Nothing synced to this device yet.")
            }
            items(documents) { DocumentCard(it, client) }
        }
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text.uppercase(), color = Dim, fontSize = 10.sp, letterSpacing = 1.5.sp,
        modifier = Modifier.padding(bottom = 8.dp),
    )
}

@Composable
private fun Honest(text: String) {
    Card(
        Modifier.fillMaxWidth().padding(bottom = 8.dp),
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(10.dp),
    ) { Text(text, color = Dim, fontSize = 12.sp, lineHeight = 17.sp, modifier = Modifier.padding(12.dp)) }
}

@Composable
private fun DeadlineCard(deadline: Json) {
    val verification = deadline["verification_status"].asString()
    Card(
        Modifier.fillMaxWidth().padding(bottom = 8.dp),
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(10.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            Text(deadline["due_date"].asString() ?: "no date", color = Text, fontSize = 15.sp,
                fontWeight = FontWeight.Bold)
            Text(deadline["title"].asString() ?: "", color = Text, fontSize = 13.sp)
            // A computed deadline is INFERENCE and names the authority that has
            // to confirm it. Showing it without that label would turn an
            // estimate into a fact somewhere between here and a hearing.
            if (verification == "INFERENCE") {
                Text(
                    "Computed, not read off a document. Confirm against the rule " +
                        "before relying on it.",
                    color = Warn, fontSize = 11.sp, lineHeight = 15.sp,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
    }
}

@Composable
private fun DocumentCard(doc: Json, client: CaseClient) {
    val uid = doc["doc_uid"].asString() ?: return
    var offline by remember(uid) {
        mutableStateOf(runCatching { client.readOffline(uid) }.getOrNull())
    }
    var busy by remember(uid) { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Card(
        Modifier.fillMaxWidth().padding(bottom = 8.dp),
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(10.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            Row {
                Text(uid, color = Accent, fontSize = 11.sp)
                Spacer(Modifier.weight(1f))
                Text(doc["document_date"].asString() ?: "no date found", color = Text, fontSize = 12.sp)
            }
            // Provenance travels with the document. On a phone, in a hallway,
            // under time pressure, this is exactly when a date's source matters.
            doc["date_source"].asString()?.let {
                Text("date read from the $it", color = Dim, fontSize = 10.sp)
            }

            Spacer(Modifier.height(6.dp))
            // The verbatim line the document was identified by — never a
            // generated summary, which could describe something the document
            // does not say.
            Text(
                doc["extract_line"].asString() ?: doc["title"].asString() ?: "",
                color = Text, fontSize = 13.sp, maxLines = 3, overflow = TextOverflow.Ellipsis,
            )
            doc["extract_locator"].asString()?.let {
                Text(it, color = Dim, fontSize = 10.sp)
            }

            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                val held = offline?.originalAvailableOffline == true
                Text(
                    if (held) "held on this device" else "not downloaded",
                    color = if (held) Good else Dim, fontSize = 11.sp,
                )
                Spacer(Modifier.weight(1f))
                if (!held) {
                    TextButton(
                        onClick = {
                            busy = true
                            scope.launch {
                                withContext(Dispatchers.IO) {
                                    runCatching {
                                        client.pin(
                                            uid,
                                            doc["sha256"].asString() ?: "",
                                            doc["original_filename"].asString() ?: uid,
                                        )
                                    }
                                }
                                offline = runCatching { client.readOffline(uid) }.getOrNull()
                                busy = false
                            }
                        },
                        enabled = !busy,
                    ) { Text(if (busy) "Saving…" else "Keep offline", color = Accent, fontSize = 12.sp) }
                }
            }
        }
    }
}

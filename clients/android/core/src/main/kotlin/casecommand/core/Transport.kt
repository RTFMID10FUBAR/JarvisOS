package casecommand.core

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.util.UUID

/** Something the client could not do. Carries the HTTP status when there was one. */
open class ClientException(message: String, val status: Int? = null) : Exception(message)

/**
 * No answer from the server. Not an error in the record — an error in the network.
 *
 * The distinction matters more than it looks. Unreachable means *fall back to
 * the device's own copy and keep working*, which is the normal state of this
 * system in a courthouse basement. Any other error means something is actually
 * wrong and the person should be told.
 */
class UnreachableException(message: String) : ClientException(message)

/**
 * This device's token no longer works.
 *
 * Never retried silently. A revoked phone that quietly keeps trying looks, to
 * the person holding it, exactly like a phone that is still syncing.
 */
class RevokedException(message: String) : ClientException(message, 403)

data class Response(val status: Int, val body: ByteArray) {
    fun text(): String = String(body, Charsets.UTF_8)
    fun json(): Json = Json.parse(text())
    override fun equals(other: Any?) = other is Response && status == other.status &&
        body.contentEquals(other.body)
    override fun hashCode() = 31 * status + body.contentHashCode()
}

/**
 * How the client reaches the server.
 *
 * An interface so tests can drive failure cases — a dropped connection, a
 * revoked token — without needing an unreliable network to reproduce them. The
 * interesting behaviour of a sync client is all in what it does when the
 * network misbehaves, so that has to be something a test can cause on purpose.
 */
interface Transport {
    fun request(
        method: String,
        url: String,
        body: ByteArray? = null,
        contentType: String? = null,
        bearer: String? = null,
    ): Response
}

/**
 * The real one. `HttpURLConnection` is in the JDK and in Android, so this same
 * class runs in the conformance harness here and on a phone unchanged.
 */
class HttpTransport(private val timeoutMillis: Int = 15_000) : Transport {
    override fun request(
        method: String,
        url: String,
        body: ByteArray?,
        contentType: String?,
        bearer: String?,
    ): Response {
        val connection = URL(url).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = timeoutMillis
            connection.readTimeout = timeoutMillis
            connection.instanceFollowRedirects = false
            contentType?.let { connection.setRequestProperty("Content-Type", it) }
            bearer?.let { connection.setRequestProperty("Authorization", "Bearer $it") }

            if (body != null) {
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(body.size)
                connection.outputStream.use { it.write(body) }
            }

            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val bytes = stream?.use { input ->
                val out = ByteArrayOutputStream()
                input.copyTo(out)
                out.toByteArray()
            } ?: ByteArray(0)
            return Response(status, bytes)
        } catch (e: SocketTimeoutException) {
            throw UnreachableException("timed out reaching $url")
        } catch (e: java.io.IOException) {
            // A refused connection and a dead DNS both land here, and both mean
            // the same thing to a phone: use what you already hold.
            throw UnreachableException(e.message ?: "could not reach $url")
        } finally {
            connection.disconnect()
        }
    }
}

/** Builds a multipart body for a capture upload. */
fun multipart(fields: Map<String, String>, filename: String, data: ByteArray): Pair<ByteArray, String> {
    val boundary = "----casecommand${UUID.randomUUID().toString().replace("-", "")}"
    val out = ByteArrayOutputStream()
    fun write(text: String) = out.write(text.toByteArray(Charsets.UTF_8))

    for ((name, value) in fields) {
        write("--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n$value\r\n")
    }
    write(
        "--$boundary\r\nContent-Disposition: form-data; name=\"file\"; " +
            "filename=\"${filename.substringAfterLast('/')}\"\r\n" +
            "Content-Type: application/octet-stream\r\n\r\n"
    )
    out.write(data)
    write("\r\n--$boundary--\r\n")
    return out.toByteArray() to "multipart/form-data; boundary=$boundary"
}

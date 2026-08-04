package casecommand.core

/**
 * A small JSON reader and writer.
 *
 * Android ships `org.json`, so this is not strictly needed there. It exists
 * because the core module has to compile and run on a plain JVM — that is what
 * makes the sync logic testable without an emulator, and testable without an
 * emulator is what makes it testable at all in an environment with no Android
 * SDK. Pulling in a JSON library would have meant a Maven dependency, and the
 * whole point of this module is that it has none.
 *
 * It handles what the Case Command API actually returns and nothing more.
 */
sealed interface Json {
    data object Null : Json
    data class Bool(val value: Boolean) : Json
    data class Num(val value: Double) : Json
    data class Str(val value: String) : Json
    data class Arr(val items: List<Json>) : Json
    data class Obj(val fields: Map<String, Json>) : Json

    companion object {
        fun parse(text: String): Json = Parser(text).let {
            val value = it.value()
            it.skipWhitespace()
            require(it.done) { "trailing content at offset ${it.offset}" }
            value
        }
    }
}

// -- convenience accessors ---------------------------------------------------
// Deliberately forgiving on read. A field the server stopped sending should
// leave the phone with a null, not a crash: a client that dies on an unexpected
// payload is a client that stops holding the record exactly when the record
// changed.
operator fun Json?.get(key: String): Json? = (this as? Json.Obj)?.fields?.get(key)
operator fun Json?.get(index: Int): Json? = (this as? Json.Arr)?.items?.getOrNull(index)

fun Json?.asString(): String? = when (this) {
    is Json.Str -> value
    is Json.Num -> if (value % 1.0 == 0.0) value.toLong().toString() else value.toString()
    is Json.Bool -> value.toString()
    else -> null
}

fun Json?.asInt(): Int? = when (this) {
    is Json.Num -> value.toInt()
    is Json.Str -> value.toIntOrNull()
    else -> null
}

fun Json?.asLong(): Long? = when (this) {
    is Json.Num -> value.toLong()
    is Json.Str -> value.toLongOrNull()
    else -> null
}

fun Json?.asBool(): Boolean = when (this) {
    is Json.Bool -> value
    is Json.Num -> value != 0.0
    else -> false
}

fun Json?.asList(): List<Json> = (this as? Json.Arr)?.items ?: emptyList()

/**
 * How many entries, whether the value is an array or an object.
 *
 * Worth having as its own function because getting it wrong is quiet. The
 * index endpoint returns `endpoints` as an object; asking `asList().size` for
 * it returned 0, and the conformance rule still passed because it only
 * asserted on `api_version`. A count that reads zero when the truth is ten is
 * exactly the kind of wrong number this whole system exists to keep off a
 * screen.
 */
fun Json?.size(): Int = when (this) {
    is Json.Arr -> items.size
    is Json.Obj -> fields.size
    else -> 0
}
fun Json?.asMap(): Map<String, Json> = (this as? Json.Obj)?.fields ?: emptyMap()

// -- writing -----------------------------------------------------------------
fun Json.write(): String = when (this) {
    is Json.Null -> "null"
    is Json.Bool -> value.toString()
    is Json.Num -> if (value % 1.0 == 0.0) value.toLong().toString() else value.toString()
    is Json.Str -> quote(value)
    is Json.Arr -> items.joinToString(",", "[", "]") { it.write() }
    is Json.Obj -> fields.entries.joinToString(",", "{", "}") { (k, v) -> "${quote(k)}:${v.write()}" }
}

fun jsonOf(vararg pairs: Pair<String, Any?>): Json.Obj =
    Json.Obj(pairs.associate { (k, v) -> k to toJson(v) })

private fun toJson(value: Any?): Json = when (value) {
    null -> Json.Null
    is Json -> value
    is Boolean -> Json.Bool(value)
    is Number -> Json.Num(value.toDouble())
    is String -> Json.Str(value)
    is List<*> -> Json.Arr(value.map { toJson(it) })
    is Map<*, *> -> Json.Obj(value.entries.associate { (k, v) -> k.toString() to toJson(v) })
    else -> Json.Str(value.toString())
}

private fun quote(text: String): String {
    val out = StringBuilder(text.length + 2)
    out.append('"')
    for (ch in text) {
        when (ch) {
            '"' -> out.append("\\\"")
            '\\' -> out.append("\\\\")
            '\n' -> out.append("\\n")
            '\r' -> out.append("\\r")
            '\t' -> out.append("\\t")
            '\b' -> out.append("\\b")
            '' -> out.append("\\f")
            else ->
                if (ch < ' ') out.append("\\u%04x".format(ch.code))
                else out.append(ch)
        }
    }
    out.append('"')
    return out.toString()
}

// -- parsing -----------------------------------------------------------------
private class Parser(private val text: String) {
    var offset = 0
    val done: Boolean get() = offset >= text.length

    fun skipWhitespace() {
        while (offset < text.length && text[offset].isWhitespace()) offset++
    }

    fun value(): Json {
        skipWhitespace()
        require(!done) { "unexpected end of input" }
        return when (val ch = text[offset]) {
            '{' -> obj()
            '[' -> arr()
            '"' -> Json.Str(string())
            't' -> literal("true", Json.Bool(true))
            'f' -> literal("false", Json.Bool(false))
            'n' -> literal("null", Json.Null)
            else ->
                if (ch == '-' || ch.isDigit()) number()
                else throw IllegalArgumentException("unexpected '$ch' at offset $offset")
        }
    }

    private fun literal(word: String, value: Json): Json {
        require(text.startsWith(word, offset)) { "expected $word at offset $offset" }
        offset += word.length
        return value
    }

    private fun obj(): Json.Obj {
        expect('{')
        val fields = LinkedHashMap<String, Json>()
        skipWhitespace()
        if (peek() == '}') { offset++; return Json.Obj(fields) }
        while (true) {
            skipWhitespace()
            val key = string()
            skipWhitespace()
            expect(':')
            fields[key] = value()
            skipWhitespace()
            when (val ch = peek()) {
                ',' -> offset++
                '}' -> { offset++; return Json.Obj(fields) }
                else -> throw IllegalArgumentException("expected , or } but found '$ch' at $offset")
            }
        }
    }

    private fun arr(): Json.Arr {
        expect('[')
        val items = ArrayList<Json>()
        skipWhitespace()
        if (peek() == ']') { offset++; return Json.Arr(items) }
        while (true) {
            items.add(value())
            skipWhitespace()
            when (val ch = peek()) {
                ',' -> offset++
                ']' -> { offset++; return Json.Arr(items) }
                else -> throw IllegalArgumentException("expected , or ] but found '$ch' at $offset")
            }
        }
    }

    private fun string(): String {
        expect('"')
        val out = StringBuilder()
        while (true) {
            require(!done) { "unterminated string" }
            when (val ch = text[offset++]) {
                '"' -> return out.toString()
                '\\' -> {
                    when (val esc = text[offset++]) {
                        '"' -> out.append('"')
                        '\\' -> out.append('\\')
                        '/' -> out.append('/')
                        'n' -> out.append('\n')
                        'r' -> out.append('\r')
                        't' -> out.append('\t')
                        'b' -> out.append('\b')
                        'f' -> out.append('')
                        'u' -> {
                            out.append(text.substring(offset, offset + 4).toInt(16).toChar())
                            offset += 4
                        }
                        else -> throw IllegalArgumentException("bad escape \\$esc at $offset")
                    }
                }
                else -> out.append(ch)
            }
        }
    }

    private fun number(): Json.Num {
        val start = offset
        if (peek() == '-') offset++
        while (!done && (text[offset].isDigit() || text[offset] in ".eE+-")) offset++
        return Json.Num(text.substring(start, offset).toDouble())
    }

    private fun peek(): Char {
        require(!done) { "unexpected end of input" }
        return text[offset]
    }

    private fun expect(ch: Char) {
        require(peek() == ch) { "expected '$ch' at offset $offset" }
        offset++
    }
}

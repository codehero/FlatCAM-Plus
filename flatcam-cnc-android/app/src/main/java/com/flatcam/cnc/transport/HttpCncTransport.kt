package com.flatcam.cnc.transport

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

class HttpCncTransport(
    baseUrl: String,
    private val user: String = "",
    private val password: String = "",
) : CncTransport {
    private val normalizedBaseUrl = normalizeBaseUrl(baseUrl)
    private var cookieHeader: String? = null
    var infoText: String = ""
        private set

    override val description: String
        get() = normalizedBaseUrl

    override suspend fun open() {
        withContext(Dispatchers.IO) {
            if (user.isNotBlank() || password.isNotBlank()) {
                val loginQuery = listOf(
                    "USER" to user,
                    "PASSWORD" to password,
                    "SUBMIT" to "yes",
                ).toQuery()
                requestText("/login?$loginQuery")
            }
            infoText = sendCommandText("[ESP800]")
        }
    }

    override suspend fun close() {
        cookieHeader = null
    }

    override suspend fun sendLine(text: String): List<String> =
        splitResponse(sendCommandText(text))

    override suspend fun sendRaw(data: ByteArray): List<String> =
        splitResponse(requestText("/command?plain=${percentEncodeBytes(data)}"))

    override suspend fun readLines(): List<String> = emptyList()

    suspend fun listFiles(endpoint: String, path: String = "/"): String {
        val query = listOf(
            "action" to "list",
            "filename" to "all",
            "path" to path.ifBlank { "/" },
        ).toQuery()
        return withContext(Dispatchers.IO) { requestText("$endpoint?$query") }
    }

    private suspend fun sendCommandText(text: String): String {
        val upper = text.trim().uppercase()
        val param = if (upper.startsWith("[ESP") || upper.startsWith("$/")) "commandText" else "plain"
        val query = listOf(param to text).toQuery()
        return withContext(Dispatchers.IO) { requestText("/command?$query") }
    }

    private fun requestText(path: String, body: String? = null): String {
        val url = URL(if (path.startsWith("/")) normalizedBaseUrl + path else "$normalizedBaseUrl/$path")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = 8000
            readTimeout = 8000
            requestMethod = if (body == null) "GET" else "POST"
            cookieHeader?.let { setRequestProperty("Cookie", it) }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            }
        }

        try {
            if (body != null) {
                OutputStreamWriter(connection.outputStream, StandardCharsets.UTF_8).use { it.write(body) }
            }
            val nextCookie = connection.headerFields["Set-Cookie"]?.joinToString("; ") {
                it.substringBefore(";")
            }
            if (!nextCookie.isNullOrBlank()) cookieHeader = nextCookie
            val stream = if (connection.responseCode >= 400) connection.errorStream else connection.inputStream
            return stream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() }.orEmpty()
        } finally {
            connection.disconnect()
        }
    }

    private fun List<Pair<String, String>>.toQuery(): String =
        joinToString("&") { (key, value) ->
            "${key.encode()}=${value.encode()}"
        }

    private fun String.encode(): String = URLEncoder.encode(this, StandardCharsets.UTF_8.name())

    private fun percentEncodeBytes(data: ByteArray): String = buildString {
        for (byte in data) {
            val value = byte.toInt() and 0xff
            val ch = value.toChar()
            if (ch.isLetterOrDigit() || ch in "-_.~") {
                append(ch)
            } else {
                append('%')
                append(value.toString(16).padStart(2, '0').uppercase())
            }
        }
    }

    companion object {
        fun normalizeBaseUrl(value: String): String {
            val trimmed = value.trim().ifBlank { "http://fluidnc.local" }
            val withScheme = if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
                trimmed
            } else {
                "http://$trimmed"
            }
            return withScheme.trimEnd('/')
        }

        fun splitResponse(response: String): List<String> =
            response.replace("\r", "\n")
                .split("\n")
                .map { it.trim() }
                .filter { it.isNotBlank() }
    }
}

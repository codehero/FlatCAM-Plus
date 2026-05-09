package com.flatcam.cnc.transport

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException
import java.nio.charset.StandardCharsets

class TcpCncTransport(
    private val host: String,
    private val port: Int,
) : CncTransport {
    private var socket: Socket? = null
    private val buffer = ArrayList<Byte>()

    override val description: String
        get() = "$host:$port"

    override suspend fun open() {
        withContext(Dispatchers.IO) {
            socket = Socket().apply {
                connect(InetSocketAddress(host, port), 4000)
                soTimeout = 60
            }
        }
    }

    override suspend fun close() {
        withContext(Dispatchers.IO) {
            runCatching { socket?.close() }
            socket = null
            buffer.clear()
        }
    }

    override suspend fun sendLine(text: String): List<String> {
        val payload = (text.trimEnd() + "\n").toByteArray(StandardCharsets.UTF_8)
        return sendRaw(payload)
    }

    override suspend fun sendRaw(data: ByteArray): List<String> {
        withContext(Dispatchers.IO) {
            val current = socket ?: error("TCP socket is closed")
            current.getOutputStream().write(data)
            current.getOutputStream().flush()
        }
        return emptyList()
    }

    override suspend fun readLines(): List<String> = withContext(Dispatchers.IO) {
        val current = socket ?: return@withContext emptyList()
        val input = current.getInputStream()
        val chunk = ByteArray(4096)

        while (true) {
            val count = try {
                input.read(chunk)
            } catch (_: SocketTimeoutException) {
                break
            }
            if (count < 0) error("TCP socket closed by remote host")
            val clean = stripTelnet(chunk.copyOf(count))
            clean.forEach { buffer.add(it) }
            if (count == 0) break
        }

        splitBufferedLines()
    }

    private fun splitBufferedLines(): List<String> {
        if (buffer.none { it == '\n'.code.toByte() || it == '\r'.code.toByte() }) return emptyList()

        val lines = mutableListOf<String>()
        val current = ArrayList<Byte>()
        val remainder = ArrayList<Byte>()
        var ended = false

        for (byte in buffer) {
            if (byte == '\n'.code.toByte() || byte == '\r'.code.toByte()) {
                if (current.isNotEmpty()) {
                    lines += current.toByteArray().toString(StandardCharsets.UTF_8).trim()
                    current.clear()
                }
                ended = true
            } else {
                if (ended) ended = false
                current += byte
            }
        }

        if (current.isNotEmpty()) {
            remainder += current
        }

        buffer.clear()
        buffer.addAll(remainder)
        return lines.filter { it.isNotBlank() }
    }

    private fun stripTelnet(data: ByteArray): ByteArray {
        val clean = ArrayList<Byte>()
        val reply = ArrayList<Byte>()
        var i = 0
        while (i < data.size) {
            val byte = data[i].toInt() and 0xff
            if (byte == IAC && i + 2 < data.size) {
                val cmd = data[i + 1].toInt() and 0xff
                val opt = data[i + 2]
                when (cmd) {
                    DO -> reply.addAll(byteArrayOf(IAC.toByte(), WONT.toByte(), opt).toList())
                    WILL -> reply.addAll(byteArrayOf(IAC.toByte(), DONT.toByte(), opt).toList())
                }
                i += 3
            } else {
                clean += data[i]
                i += 1
            }
        }
        if (reply.isNotEmpty()) {
            runCatching { socket?.getOutputStream()?.write(reply.toByteArray()) }
        }
        return clean.toByteArray()
    }

    companion object {
        private const val IAC = 255
        private const val DO = 253
        private const val DONT = 254
        private const val WILL = 251
        private const val WONT = 252
    }
}

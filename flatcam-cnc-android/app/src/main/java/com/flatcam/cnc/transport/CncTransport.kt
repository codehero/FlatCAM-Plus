package com.flatcam.cnc.transport

interface CncTransport {
    val description: String
    suspend fun open()
    suspend fun close()
    suspend fun sendLine(text: String): List<String>
    suspend fun sendRaw(data: ByteArray): List<String>
    suspend fun readLines(): List<String>
}

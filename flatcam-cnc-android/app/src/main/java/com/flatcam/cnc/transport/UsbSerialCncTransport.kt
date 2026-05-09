package com.flatcam.cnc.transport

import android.content.Context
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbManager
import com.hoho.android.usbserial.driver.UsbSerialPort
import com.hoho.android.usbserial.driver.UsbSerialProber
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.nio.charset.StandardCharsets

data class UsbDeviceOption(
    val deviceId: Int,
    val label: String,
)

class UsbSerialCncTransport(
    private val context: Context,
    private val deviceId: Int?,
    private val baudRate: Int,
) : CncTransport {
    private var connection: UsbDeviceConnection? = null
    private var port: UsbSerialPort? = null
    private val lineBuffer = ArrayList<Byte>()

    override val description: String
        get() = "USB Serial @ $baudRate"

    override suspend fun open() {
        withContext(Dispatchers.IO) {
            val manager = context.getSystemService(Context.USB_SERVICE) as UsbManager
            val drivers = UsbSerialProber.getDefaultProber().findAllDrivers(manager)
            val driver = drivers.firstOrNull { deviceId == null || it.device.deviceId == deviceId }
                ?: error("USB serial device not found")

            val broker = UsbPermissionBroker(context, manager)
            if (!broker.ensurePermission(driver.device)) error("USB permission was denied")

            val usbConnection = manager.openDevice(driver.device) ?: error("USB device cannot be opened")
            val serialPort = driver.ports.firstOrNull() ?: error("USB serial port not found")
            serialPort.open(usbConnection)
            serialPort.setParameters(
                baudRate,
                8,
                UsbSerialPort.STOPBITS_1,
                UsbSerialPort.PARITY_NONE,
            )
            serialPort.dtr = true
            serialPort.rts = true

            connection = usbConnection
            port = serialPort
        }
    }

    override suspend fun close() {
        withContext(Dispatchers.IO) {
            runCatching { port?.close() }
            runCatching { connection?.close() }
            port = null
            connection = null
            lineBuffer.clear()
        }
    }

    override suspend fun sendLine(text: String): List<String> {
        val payload = (text.trimEnd() + "\n").toByteArray(StandardCharsets.UTF_8)
        return sendRaw(payload)
    }

    override suspend fun sendRaw(data: ByteArray): List<String> {
        withContext(Dispatchers.IO) {
            val serialPort = port ?: error("USB serial port is closed")
            serialPort.write(data, 1000)
        }
        return emptyList()
    }

    override suspend fun readLines(): List<String> = withContext(Dispatchers.IO) {
        val serialPort = port ?: return@withContext emptyList()
        val buffer = ByteArray(4096)
        val count = runCatching { serialPort.read(buffer, 80) }.getOrDefault(0)
        if (count > 0) {
            buffer.copyOf(count).forEach { lineBuffer.add(it) }
        }
        splitBufferedLines()
    }

    private fun splitBufferedLines(): List<String> {
        if (lineBuffer.none { it == '\n'.code.toByte() || it == '\r'.code.toByte() }) return emptyList()
        val lines = mutableListOf<String>()
        val current = ArrayList<Byte>()
        val remainder = ArrayList<Byte>()

        for (byte in lineBuffer) {
            if (byte == '\n'.code.toByte() || byte == '\r'.code.toByte()) {
                if (current.isNotEmpty()) {
                    lines += current.toByteArray().toString(StandardCharsets.UTF_8).trim()
                    current.clear()
                }
            } else {
                current += byte
            }
        }
        if (current.isNotEmpty()) remainder += current

        lineBuffer.clear()
        lineBuffer.addAll(remainder)
        return lines.filter { it.isNotBlank() }
    }

    companion object {
        fun listDevices(context: Context): List<UsbDeviceOption> {
            val manager = context.getSystemService(Context.USB_SERVICE) as UsbManager
            return UsbSerialProber.getDefaultProber().findAllDrivers(manager).map { driver ->
                val device = driver.device
                val vendor = device.vendorId.toString(16).padStart(4, '0')
                val product = device.productId.toString(16).padStart(4, '0')
                UsbDeviceOption(device.deviceId, "${device.deviceName}  VID:$vendor PID:$product")
            }
        }
    }
}

package com.flatcam.cnc.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.flatcam.cnc.domain.CncCommand
import com.flatcam.cnc.domain.CncProfile
import com.flatcam.cnc.domain.CncStatus
import com.flatcam.cnc.domain.MachineProfile
import com.flatcam.cnc.domain.calculateGCodeStats
import com.flatcam.cnc.domain.isControllerAck
import com.flatcam.cnc.domain.normalizedGCodeLines
import com.flatcam.cnc.domain.parseSdFileLine
import com.flatcam.cnc.domain.updatedByControllerLine
import com.flatcam.cnc.transport.CncTransport
import com.flatcam.cnc.transport.ConnectionMode
import com.flatcam.cnc.transport.HttpCncTransport
import com.flatcam.cnc.transport.TcpCncTransport
import com.flatcam.cnc.transport.UsbDeviceOption
import com.flatcam.cnc.transport.UsbSerialCncTransport
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject

enum class AppTab(val label: String) {
    CONNECTION("Bağlantı"),
    CONTROL("Kontrol"),
    JOB("İş"),
    CONSOLE("Konsol"),
}

enum class ConsoleType {
    TX,
    RX,
    INFO,
    WARN,
    ERROR,
}

data class ConsoleEntry(
    val text: String,
    val type: ConsoleType,
    val time: String = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date()),
)

data class CncUiState(
    val selectedTab: AppTab = AppTab.CONNECTION,
    val connectionMode: ConnectionMode = ConnectionMode.HTTP,
    val profile: CncProfile = CncProfile.FLUIDNC,
    val machineProfile: MachineProfile = MachineProfile(),
    val webUrl: String = "http://fluidnc.local",
    val tcpHost: String = "192.168.0.1",
    val tcpPort: String = "23",
    val user: String = "",
    val password: String = "",
    val baudRate: String = "115200",
    val usbDevices: List<UsbDeviceOption> = emptyList(),
    val selectedUsbDeviceId: Int? = null,
    val connected: Boolean = false,
    val connecting: Boolean = false,
    val connectionDescription: String = "Offline",
    val status: CncStatus = CncStatus(),
    val controllerInfo: Map<String, String> = emptyMap(),
    val console: List<ConsoleEntry> = emptyList(),
    val commandEntry: String = "",
    val hideStatusReports: Boolean = true,
    val jogStep: Double = 1.0,
    val jogFeed: Int = 1000,
    val feedOverride: Int = 100,
    val spindleOverride: Int = 100,
    val spindleRpm: Int = 8000,
    val laserOn: Boolean = false,
    val gcodeText: String = "",
    val streamProgress: Float = 0f,
    val streaming: Boolean = false,
    val streamPaused: Boolean = false,
    val sdFiles: List<String> = emptyList(),
    val selectedSdFile: String = "",
    val remoteFiles: List<String> = emptyList(),
) {
    val gcodeStats = calculateGCodeStats(gcodeText)
}

class CncViewModel(application: Application) : AndroidViewModel(application) {
    private val _uiState = MutableStateFlow(
        CncUiState(
            console = listOf(ConsoleEntry("FlatCAM CNC mobil arayüz hazır.", ConsoleType.INFO))
        )
    )
    val uiState: StateFlow<CncUiState> = _uiState

    private var transport: CncTransport? = null
    private var receiveJob: Job? = null
    private var statusJob: Job? = null
    private var streamingJob: Job? = null
    private var sdCollecting = false
    private val ioMutex = Mutex()
    private val ackChannel = Channel<String>(Channel.UNLIMITED)

    init {
        refreshUsbDevices()
    }

    override fun onCleared() {
        viewModelScope.launch { disconnectInternal(emitLog = false) }
        super.onCleared()
    }

    fun selectTab(tab: AppTab) = _uiState.update { it.copy(selectedTab = tab) }

    fun setConnectionMode(mode: ConnectionMode) = _uiState.update { it.copy(connectionMode = mode) }

    fun setProfile(profile: CncProfile) = _uiState.update { it.copy(profile = profile) }

    fun setWebUrl(value: String) = _uiState.update { it.copy(webUrl = value) }

    fun setTcpHost(value: String) = _uiState.update { it.copy(tcpHost = value) }

    fun setTcpPort(value: String) = _uiState.update { it.copy(tcpPort = value.filter { ch -> ch.isDigit() }) }

    fun setUser(value: String) = _uiState.update { it.copy(user = value) }

    fun setPassword(value: String) = _uiState.update { it.copy(password = value) }

    fun setBaudRate(value: String) = _uiState.update { it.copy(baudRate = value.filter { ch -> ch.isDigit() }) }

    fun selectUsbDevice(deviceId: Int?) = _uiState.update { it.copy(selectedUsbDeviceId = deviceId) }

    fun setCommandEntry(value: String) = _uiState.update { it.copy(commandEntry = value) }

    fun setHideStatusReports(value: Boolean) = _uiState.update { it.copy(hideStatusReports = value) }

    fun setJogStep(value: Double) = _uiState.update { it.copy(jogStep = value.coerceIn(0.01, 100.0)) }

    fun setJogFeed(value: Int) = _uiState.update { it.copy(jogFeed = value.coerceIn(1, 60000)) }

    fun setFeedOverride(value: Int) = _uiState.update { it.copy(feedOverride = value.coerceIn(10, 200)) }

    fun setSpindleOverride(value: Int) = _uiState.update { it.copy(spindleOverride = value.coerceIn(10, 200)) }

    fun setSpindleRpm(value: Int) = _uiState.update { state ->
        state.copy(spindleRpm = value.coerceIn(0, state.machineProfile.spindleMax.coerceAtLeast(1)))
    }

    fun setGCodeText(value: String) = _uiState.update { it.copy(gcodeText = value) }

    fun selectSdFile(value: String) = _uiState.update { it.copy(selectedSdFile = value) }

    fun refreshUsbDevices() {
        viewModelScope.launch(Dispatchers.IO) {
            val devices = runCatching { UsbSerialCncTransport.listDevices(getApplication()) }.getOrDefault(emptyList())
            _uiState.update { state ->
                val selected = state.selectedUsbDeviceId?.takeIf { id -> devices.any { it.deviceId == id } }
                    ?: devices.firstOrNull()?.deviceId
                state.copy(usbDevices = devices, selectedUsbDeviceId = selected)
            }
        }
    }

    fun connect() {
        val snapshot = _uiState.value
        if (snapshot.connected || snapshot.connecting) return

        viewModelScope.launch {
            _uiState.update { it.copy(connecting = true) }
            appendConsole("Bağlanıyor...", ConsoleType.INFO)

            val result = runCatching {
                val nextTransport = buildTransport(snapshot)
                nextTransport.open()
                transport = nextTransport
                _uiState.update {
                    it.copy(
                        connected = true,
                        connecting = false,
                        connectionDescription = nextTransport.description,
                        status = it.status.copy(state = "Idle"),
                    )
                }
                appendConsole("Bağlandı: ${nextTransport.description}", ConsoleType.INFO)
                startBackgroundLoops()
                if (nextTransport is HttpCncTransport && nextTransport.infoText.isNotBlank()) {
                    updateControllerInfo(nextTransport.infoText)
                } else {
                    sendProfileCommand("info", log = false)
                }
                if (nextTransport is HttpCncTransport) refreshHttpFiles()
            }

            result.onFailure { error ->
                appendConsole("Bağlantı başarısız: ${error.message}", ConsoleType.ERROR)
                runCatching { transport?.close() }
                transport = null
                _uiState.update {
                    it.copy(
                        connected = false,
                        connecting = false,
                        connectionDescription = "Offline",
                        status = CncStatus(),
                    )
                }
            }
        }
    }

    fun testConnection() {
        val snapshot = _uiState.value
        if (snapshot.connected || snapshot.connecting) return
        viewModelScope.launch {
            _uiState.update { it.copy(connecting = true) }
            appendConsole("Bağlantı testi başlıyor...", ConsoleType.INFO)
            val result = runCatching {
                val testTransport = buildTransport(snapshot)
                testTransport.open()
                val description = testTransport.description
                testTransport.close()
                description
            }
            result.onSuccess { appendConsole("Test başarılı: $it", ConsoleType.INFO) }
            result.onFailure { appendConsole("Test başarısız: ${it.message}", ConsoleType.ERROR) }
            _uiState.update { it.copy(connecting = false) }
        }
    }

    fun disconnect() {
        viewModelScope.launch { disconnectInternal() }
    }

    fun sendManualCommand() {
        val commandText = _uiState.value.commandEntry
        if (commandText.isBlank()) return
        _uiState.update { it.copy(commandEntry = "") }
        viewModelScope.launch {
            commandText.lines().map { it.trim() }.filter { it.isNotBlank() }.forEach { line ->
                sendCommandLine(line)
            }
        }
    }

    fun executeProfileCommand(key: String, log: Boolean = true) {
        viewModelScope.launch { sendProfileCommand(key, log) }
    }

    fun home() {
        _uiState.update { it.copy(status = it.status.copy(state = "Homing")) }
        executeProfileCommand("home")
    }

    fun zeroAxis(axis: Char) {
        viewModelScope.launch { sendCncCommand(_uiState.value.profile.zeroAxis(axis)) }
    }

    fun zeroAll() {
        viewModelScope.launch { sendCncCommand(_uiState.value.profile.command("zero_all")) }
    }

    fun jog(axis: Char, direction: Int) {
        val state = _uiState.value
        val distance = state.jogStep * direction
        viewModelScope.launch {
            sendCncCommand(state.profile.jog(axis, distance, state.jogFeed))
        }
    }

    fun applyFeedOverride() {
        val state = _uiState.value
        viewModelScope.launch { sendCncCommand(state.profile.feedOverride(state.feedOverride)) }
    }

    fun applySpindleOverride() {
        val state = _uiState.value
        viewModelScope.launch { sendCncCommand(state.profile.spindleOverride(state.spindleOverride)) }
    }

    fun setSpindleSpeed() {
        val state = _uiState.value
        viewModelScope.launch { sendCncCommand(state.profile.spindleRpm(state.spindleRpm)) }
    }

    fun toggleLaser() {
        val next = !_uiState.value.laserOn
        _uiState.update { it.copy(laserOn = next) }
        executeProfileCommand(if (next) "laser_on" else "laser_off")
    }

    fun refreshSdList() {
        _uiState.update { it.copy(sdFiles = emptyList(), selectedSdFile = "") }
        sdCollecting = false
        executeProfileCommand("sd_list")
        refreshHttpFiles()
    }

    fun runSelectedSdFile() {
        val state = _uiState.value
        val file = state.selectedSdFile.ifBlank { state.sdFiles.firstOrNull().orEmpty() }
        if (file.isBlank()) {
            appendConsole("SD dosyası seçilmedi.", ConsoleType.WARN)
            return
        }
        viewModelScope.launch {
            val command = state.profile.runSd(file)
            if (command == null) appendConsole("Seçili profilde SD çalıştırma desteklenmiyor.", ConsoleType.WARN)
            sendCncCommand(command)
        }
    }

    fun refreshHttpFiles() {
        val currentTransport = transport as? HttpCncTransport ?: return
        viewModelScope.launch {
            val result = runCatching { currentTransport.listFiles("/files", "/") }
            result.onSuccess { payload ->
                _uiState.update { it.copy(remoteFiles = parseRemoteFiles(payload)) }
            }
            result.onFailure { appendConsole("HTTP dosya listesi alınamadı: ${it.message}", ConsoleType.WARN) }
        }
    }

    fun loadSampleGCode() {
        val sample = """
            G21
            G90
            G0 X0 Y0 Z5
            G0 X5 Y5
            G1 Z-0.1 F120
            G1 X35 Y5 F500
            G1 X35 Y25
            G1 X5 Y25
            G1 X5 Y5
            G0 Z5
            M5
        """.trimIndent()
        _uiState.update { it.copy(gcodeText = sample) }
    }

    fun startStream() {
        val state = _uiState.value
        if (!state.connected) {
            appendConsole("Kontrolcü bağlı değil.", ConsoleType.ERROR)
            return
        }
        if (state.streaming) return

        val lines = normalizedGCodeLines(state.gcodeText)
        if (lines.isEmpty()) {
            appendConsole("Gönderilecek G-code yok.", ConsoleType.WARN)
            return
        }

        streamingJob?.cancel()
        streamingJob = viewModelScope.launch {
            _uiState.update { it.copy(streaming = true, streamPaused = false, streamProgress = 0f) }
            appendConsole("İş gönderimi başladı: ${lines.size} satır", ConsoleType.INFO)
            var sent = 0
            var stoppedByError = false
            for (line in lines) {
                while (_uiState.value.streamPaused && _uiState.value.streaming) delay(100)
                if (!_uiState.value.streaming) break
                val ok = sendAndAwaitAck(line)
                if (!ok) {
                    stoppedByError = true
                    break
                }
                sent += 1
                _uiState.update { it.copy(streamProgress = sent.toFloat() / lines.size.toFloat()) }
            }
            val completed = sent == lines.size && !stoppedByError
            _uiState.update {
                it.copy(
                    streaming = false,
                    streamPaused = false,
                    streamProgress = if (completed) 1f else it.streamProgress,
                )
            }
            appendConsole(if (completed) "İş tamamlandı." else "İş durdu.", if (completed) ConsoleType.INFO else ConsoleType.WARN)
        }
    }

    fun toggleStreamPause() {
        if (!_uiState.value.streaming) return
        val paused = !_uiState.value.streamPaused
        _uiState.update { it.copy(streamPaused = paused) }
        executeProfileCommand(if (paused) "hold" else "resume")
    }

    fun stopStream() {
        if (!_uiState.value.streaming) return
        streamingJob?.cancel()
        _uiState.update { it.copy(streaming = false, streamPaused = false) }
        executeProfileCommand("hold")
        appendConsole("İş gönderimi durduruldu.", ConsoleType.WARN)
    }

    fun clearConsole() {
        _uiState.update { it.copy(console = emptyList()) }
    }

    private fun buildTransport(state: CncUiState): CncTransport = when (state.connectionMode) {
        ConnectionMode.HTTP -> HttpCncTransport(state.webUrl, state.user, state.password)
        ConnectionMode.TCP -> TcpCncTransport(state.tcpHost, state.tcpPort.toIntOrNull() ?: 23)
        ConnectionMode.USB_SERIAL -> UsbSerialCncTransport(
            context = getApplication(),
            deviceId = state.selectedUsbDeviceId,
            baudRate = state.baudRate.toIntOrNull() ?: 115200,
        )
    }

    private fun startBackgroundLoops() {
        receiveJob?.cancel()
        statusJob?.cancel()
        receiveJob = viewModelScope.launch(Dispatchers.IO) {
            while (isActive && _uiState.value.connected) {
                val lines = runCatching {
                    ioMutex.withLock { transport?.readLines().orEmpty() }
                }.getOrElse { error ->
                    appendConsole("Okuma hatası: ${error.message}", ConsoleType.ERROR)
                    disconnectInternal()
                    emptyList()
                }
                lines.forEach { handleLine(it) }
                delay(35)
            }
        }

        statusJob = viewModelScope.launch {
            while (isActive && _uiState.value.connected) {
                delay(if (_uiState.value.connectionMode == ConnectionMode.HTTP) 1000 else 350)
                pollStatus()
            }
        }
    }

    private suspend fun pollStatus() {
        val profile = _uiState.value.profile
        val raw = profile.command("status_raw")
        if (raw?.raw != null) {
            sendRawBytes(raw.raw, log = false)
        } else {
            val status = profile.command("status")
            sendCncCommand(status, log = false)
        }
    }

    private suspend fun disconnectInternal(emitLog: Boolean = true) {
        receiveJob?.cancel()
        statusJob?.cancel()
        streamingJob?.cancel()
        receiveJob = null
        statusJob = null
        streamingJob = null
        val current = transport
        transport = null
        runCatching { ioMutex.withLock { current?.close() } }
        _uiState.update {
            it.copy(
                connected = false,
                connecting = false,
                connectionDescription = "Offline",
                status = CncStatus(),
                streaming = false,
                streamPaused = false,
            )
        }
        if (emitLog) appendConsole("Bağlantı kapandı.", ConsoleType.INFO)
    }

    private suspend fun sendProfileCommand(key: String, log: Boolean = true) {
        val command = _uiState.value.profile.command(key)
        if (command == null) {
            if (log) appendConsole("$key seçili profilde desteklenmiyor.", ConsoleType.WARN)
            return
        }
        sendCncCommand(command, log)
    }

    private suspend fun sendCncCommand(command: CncCommand?, log: Boolean = true) {
        if (command == null) return
        command.raw?.let {
            sendRawBytes(it, log = log)
            return
        }
        command.lines.forEach { sendCommandLine(it, log = log) }
    }

    private suspend fun sendCommandLine(line: String, log: Boolean = true) {
        val current = transport
        if (!_uiState.value.connected || current == null) {
            if (log) appendConsole("Kontrolcü bağlı değil.", ConsoleType.ERROR)
            return
        }
        if (log) appendConsole(line, ConsoleType.TX)
        val result = runCatching { ioMutex.withLock { current.sendLine(line) } }
        result.onSuccess { responses -> responses.forEach { handleLine(it, echo = true) } }
        result.onFailure {
            appendConsole("İletişim hatası: ${it.message}", ConsoleType.ERROR)
            disconnectInternal()
        }
    }

    private suspend fun sendRawBytes(data: ByteArray, log: Boolean = true) {
        val current = transport
        if (!_uiState.value.connected || current == null) {
            if (log) appendConsole("Kontrolcü bağlı değil.", ConsoleType.ERROR)
            return
        }
        if (log) appendConsole("<raw ${data.size} byte>", ConsoleType.TX)
        val result = runCatching { ioMutex.withLock { current.sendRaw(data) } }
        result.onSuccess { responses -> responses.forEach { handleLine(it, echo = true) } }
        result.onFailure {
            appendConsole("İletişim hatası: ${it.message}", ConsoleType.ERROR)
            disconnectInternal()
        }
    }

    private suspend fun sendAndAwaitAck(line: String): Boolean {
        drainAcks()
        sendCommandLine(line)
        val ack = withTimeoutOrNull(30000) { ackChannel.receive() }
        if (ack == null) {
            appendConsole("Kontrolcü yanıt süresi doldu: $line", ConsoleType.ERROR)
            return false
        }
        if (ack.lowercase(Locale.US).startsWith("error") || ack.lowercase(Locale.US).startsWith("alarm")) {
            appendConsole("Kontrolcü komutu reddetti: $line", ConsoleType.ERROR)
            return false
        }
        return true
    }

    private fun drainAcks() {
        while (ackChannel.tryReceive().isSuccess) {
            // Drop stale acknowledgements before a streaming send.
        }
    }

    private fun handleLine(line: String, echo: Boolean = false) {
        val clean = line.trim()
        if (clean.isBlank()) return

        val status = _uiState.value.status.updatedByControllerLine(clean)
        val isStatusLine = status != null
        if (status != null) {
            _uiState.update { it.copy(status = status) }
        }

        val (sdFile, collecting) = parseSdFileLine(clean, sdCollecting)
        sdCollecting = collecting
        if (!sdFile.isNullOrBlank()) {
            _uiState.update { state ->
                val files = (state.sdFiles + sdFile).distinct()
                state.copy(sdFiles = files, selectedSdFile = state.selectedSdFile.ifBlank { sdFile })
            }
        }

        if (isControllerAck(clean)) {
            ackChannel.trySend(clean)
        }

        if (!isStatusLine || !_uiState.value.hideStatusReports || echo) {
            appendConsole(clean, ConsoleType.RX)
        }
    }

    private fun updateControllerInfo(text: String) {
        val info = text.replace("\r", "\n")
            .replace("\n", "#")
            .split("#")
            .mapNotNull { chunk ->
                val idx = chunk.indexOf(":")
                if (idx <= 0) null else chunk.substring(0, idx).trim() to chunk.substring(idx + 1).trim()
            }
            .filter { it.first.isNotBlank() }
            .toMap()
        if (info.isNotEmpty()) {
            _uiState.update { it.copy(controllerInfo = info) }
        }
    }

    private fun parseRemoteFiles(payload: String): List<String> {
        val result = mutableListOf<String>()
        runCatching {
            val json = JSONObject(payload)
            val files = json.optJSONArray("files") ?: return@runCatching
            for (index in 0 until files.length()) {
                val item = files.get(index)
                val name = when (item) {
                    is JSONObject -> item.optString("name").ifBlank { item.optString("filename") }
                    else -> item.toString()
                }
                if (name.isNotBlank()) result += name
            }
        }
        return result.distinct()
    }

    private fun appendConsole(text: String, type: ConsoleType) {
        _uiState.update { state ->
            state.copy(console = (state.console + ConsoleEntry(text, type)).takeLast(500))
        }
    }
}

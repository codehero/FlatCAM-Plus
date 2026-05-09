package com.flatcam.cnc.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Cable
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.ContentPaste
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowLeft
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Report
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Terminal
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.flatcam.cnc.domain.CncProfile
import com.flatcam.cnc.domain.GCodeStats
import com.flatcam.cnc.transport.ConnectionMode
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CncApp(viewModel: CncViewModel) {
    val state by viewModel.uiState.collectAsState()

    FlatCamTheme {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        Column {
                            Text(
                                if (state.selectedTab == AppTab.CONNECTION) "FlatCAM CNC" else state.selectedTab.label,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                fontWeight = FontWeight.Bold,
                            )
                            Text(
                                state.connectionDescription,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    },
                    actions = {
                        StatusDot(state.status.normalizedState)
                        Surface(
                            modifier = Modifier.padding(end = 12.dp),
                            shape = CircleShape,
                            color = MaterialTheme.colorScheme.surfaceVariant,
                        ) {
                            IconButton(onClick = { viewModel.refreshUsbDevices() }) {
                                Icon(Icons.Default.Settings, contentDescription = "Ayarlar")
                            }
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
                )
            },
            bottomBar = {
                NavigationBar(containerColor = Color.White) {
                    AppTab.entries.forEach { tab ->
                        NavigationBarItem(
                            selected = state.selectedTab == tab,
                            onClick = { viewModel.selectTab(tab) },
                            icon = {
                                Icon(
                                    when (tab) {
                                        AppTab.CONNECTION -> Icons.Default.Cable
                                        AppTab.CONTROL -> Icons.Default.Tune
                                        AppTab.JOB -> Icons.Default.PlayArrow
                                        AppTab.CONSOLE -> Icons.Default.Terminal
                                    },
                                    contentDescription = tab.label,
                                )
                            },
                            label = { Text(tab.label) },
                        )
                    }
                }
            }
        ) { padding ->
            Surface(
                modifier = Modifier
                    .padding(padding)
                    .fillMaxSize(),
                color = MaterialTheme.colorScheme.background,
            ) {
                when (state.selectedTab) {
                    AppTab.CONNECTION -> ConnectionScreen(state, viewModel)
                    AppTab.CONTROL -> ControlScreen(state, viewModel)
                    AppTab.JOB -> JobScreen(state, viewModel)
                    AppTab.CONSOLE -> ConsoleScreen(state, viewModel)
                }
            }
        }
    }
}

@Composable
private fun FlatCamTheme(content: @Composable () -> Unit) {
    val colorScheme = lightColorScheme(
        primary = Color(0xFF0D9488),
        secondary = Color(0xFF475569),
        tertiary = Color(0xFFF97316),
        error = Color(0xFFB3261E),
        background = Color(0xFFF8FAFC),
        surface = Color(0xFFFFFFFF),
        surfaceVariant = Color(0xFFF1F5F9),
    )
    MaterialTheme(colorScheme = colorScheme, typography = androidx.compose.material3.Typography(), content = content)
}

@Composable
private fun ConnectionScreen(state: CncUiState, viewModel: CncViewModel) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        ConnectionHero(state)

        Panel(title = "Bağlantı", icon = Icons.Default.Cable) {
            Text("Mod", style = MaterialTheme.typography.labelLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                ConnectionMode.entries.forEach { mode ->
                    FilterChip(
                        selected = state.connectionMode == mode,
                        onClick = { viewModel.setConnectionMode(mode) },
                        label = { Text(mode.label, maxLines = 1) },
                    )
                }
            }

            Spacer(Modifier.height(8.dp))
            SelectField(
                label = "Kontrolcü profili",
                value = state.profile.label,
                options = CncProfile.entries,
                optionLabel = { it.label },
                onSelect = viewModel::setProfile,
            )

            when (state.connectionMode) {
                ConnectionMode.HTTP -> {
                    TextFieldLine("URL", state.webUrl, viewModel::setWebUrl)
                    TextFieldLine("Kullanıcı", state.user, viewModel::setUser)
                    TextFieldLine(
                        label = "Parola",
                        value = state.password,
                        onValueChange = viewModel::setPassword,
                        password = true,
                    )
                }
                ConnectionMode.TCP -> {
                    TextFieldLine("Host", state.tcpHost, viewModel::setTcpHost)
                    TextFieldLine(
                        label = "Port",
                        value = state.tcpPort,
                        onValueChange = viewModel::setTcpPort,
                        keyboardType = KeyboardType.Number,
                    )
                }
                ConnectionMode.USB_SERIAL -> {
                    TextFieldLine(
                        label = "Baud",
                        value = state.baudRate,
                        onValueChange = viewModel::setBaudRate,
                        keyboardType = KeyboardType.Number,
                    )
                    SelectField(
                        label = "USB cihaz",
                        value = state.usbDevices.firstOrNull { it.deviceId == state.selectedUsbDeviceId }?.label
                            ?: "Cihaz yok",
                        options = state.usbDevices,
                        optionLabel = { it.label },
                        onSelect = { viewModel.selectUsbDevice(it.deviceId) },
                    )
                    TextButton(onClick = viewModel::refreshUsbDevices) {
                        Icon(Icons.Default.Refresh, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("USB yenile")
                    }
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                Button(
                    onClick = { if (state.connected) viewModel.disconnect() else viewModel.connect() },
                    enabled = !state.connecting,
                    modifier = Modifier.weight(1f),
                ) {
                    Icon(Icons.Default.Cable, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text(if (state.connected) "Kes" else "Bağlan")
                }
                OutlinedButton(
                    onClick = viewModel::testConnection,
                    enabled = !state.connected && !state.connecting,
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Test")
                }
            }
        }

        Panel(title = "Makine", icon = Icons.Default.Settings) {
            InfoRow("Profil", state.machineProfile.name)
            InfoRow("Güvenli Z", "${state.machineProfile.safeZ} mm")
            InfoRow("Jog feed", "${state.machineProfile.jogFeed} mm/min")
            InfoRow("Maks. spindle", "${state.machineProfile.spindleMax} RPM")
            InfoRow(
                "Alan",
                "${state.machineProfile.travelX} x ${state.machineProfile.travelY} x ${state.machineProfile.travelZ} mm",
            )
        }

        if (state.controllerInfo.isNotEmpty()) {
            Panel(title = "Kontrolcü", icon = Icons.Default.Terminal) {
                state.controllerInfo.entries.take(8).forEach { (key, value) ->
                    InfoRow(key, value)
                }
            }
        }
    }
}

@Composable
private fun ControlScreen(state: CncUiState, viewModel: CncViewModel) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        GaugeOverview(state)

        DarkDroPanel(state, viewModel)
/*
                Text("XYZ sıfırla")
*/
        Panel(title = "Jog", icon = Icons.Default.Tune) {
            SliderRow(
                label = "Adım",
                value = state.jogStep.toFloat(),
                range = 0.1f..20f,
                display = "${"%.2f".format(Locale.US, state.jogStep)} mm",
                onChange = { viewModel.setJogStep(it.toDouble()) },
            )
            SliderRow(
                label = "Feed",
                value = state.jogFeed.toFloat(),
                range = 50f..5000f,
                display = "${state.jogFeed} mm/min",
                onChange = { viewModel.setJogFeed(it.toInt()) },
            )
            JogPad(viewModel)
        }

        Panel(title = "Komutlar", icon = Icons.Default.Bolt) {
            ActionGrid(
                listOf(
                    ActionSpec("Home", Icons.Default.Home, viewModel::home),
                    ActionSpec("Unlock", Icons.Default.Bolt) { viewModel.executeProfileCommand("unlock") },
                    ActionSpec("Reset", Icons.Default.Report) { viewModel.executeProfileCommand("reset") },
                    ActionSpec("Hold", Icons.Default.Pause) { viewModel.executeProfileCommand("hold") },
                    ActionSpec("Resume", Icons.Default.PlayArrow) { viewModel.executeProfileCommand("resume") },
                    ActionSpec("Info", Icons.Default.Settings) { viewModel.executeProfileCommand("info") },
                )
            )
        }

        Panel(title = "Spindle / Override", icon = Icons.Default.Settings) {
            SliderRow("Feed override", state.feedOverride.toFloat(), 10f..200f, "${state.feedOverride}%") {
                viewModel.setFeedOverride(it.toInt())
            }
            Button(onClick = viewModel::applyFeedOverride, modifier = Modifier.fillMaxWidth()) {
                Text("Feed override uygula")
            }
            SliderRow("Spindle override", state.spindleOverride.toFloat(), 10f..200f, "${state.spindleOverride}%") {
                viewModel.setSpindleOverride(it.toInt())
            }
            Button(onClick = viewModel::applySpindleOverride, modifier = Modifier.fillMaxWidth()) {
                Text("Spindle override uygula")
            }
            SliderRow("Spindle", state.spindleRpm.toFloat(), 0f..state.machineProfile.spindleMax.toFloat(), "${state.spindleRpm} RPM") {
                viewModel.setSpindleRpm(it.toInt())
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                Button(onClick = viewModel::setSpindleSpeed, modifier = Modifier.weight(1f)) {
                    Text("M3 S")
                }
                OutlinedButton(onClick = { viewModel.executeProfileCommand("spindle_stop") }, modifier = Modifier.weight(1f)) {
                    Text("M5")
                }
                Button(
                    onClick = viewModel::toggleLaser,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (state.laserOn) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
                    ),
                    modifier = Modifier.weight(1f),
                ) {
                    Text(if (state.laserOn) "Laser kapat" else "Laser aç")
                }
            }
        }
    }
}

@Composable
private fun JobScreen(state: CncUiState, viewModel: CncViewModel) {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) {
            val text = context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }.orEmpty()
            viewModel.setGCodeText(text)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        JobStatusCard(state)

        Panel(title = "G-code", icon = Icons.Default.ContentPaste) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(onClick = { launcher.launch("*/*") }, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.FolderOpen, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Dosya aç")
                }
                OutlinedButton(onClick = viewModel::loadSampleGCode, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.ContentPaste, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Örnek")
                }
            }
            OutlinedTextField(
                value = state.gcodeText,
                onValueChange = viewModel::setGCodeText,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 220.dp),
                textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                label = { Text("Program") },
                minLines = 10,
            )
            GCodeStatsView(state.gcodeStats)
        }

        Panel(title = "Gönderim", icon = Icons.Default.PlayArrow) {
            LinearProgressIndicator(progress = { state.streamProgress }, modifier = Modifier.fillMaxWidth())
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                Button(onClick = viewModel::startStream, enabled = !state.streaming, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Başlat")
                }
                OutlinedButton(onClick = viewModel::toggleStreamPause, enabled = state.streaming, modifier = Modifier.weight(1f)) {
                    Icon(if (state.streamPaused) Icons.Default.PlayArrow else Icons.Default.Pause, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text(if (state.streamPaused) "Sürdür" else "Duraklat")
                }
                OutlinedButton(onClick = viewModel::stopStream, enabled = state.streaming, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.Stop, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Stop")
                }
            }
        }

        Panel(title = "SD / Dosyalar", icon = Icons.Default.FolderOpen) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(onClick = viewModel::refreshSdList, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.Refresh, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Listele")
                }
                Button(onClick = viewModel::runSelectedSdFile, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("SD çalıştır")
                }
            }
            SelectField(
                label = "SD dosyası",
                value = state.selectedSdFile.ifBlank { "Seçim yok" },
                options = state.sdFiles,
                optionLabel = { it },
                onSelect = viewModel::selectSdFile,
            )
            if (state.remoteFiles.isNotEmpty()) {
                Text("HTTP dosyaları", style = MaterialTheme.typography.labelLarge)
                state.remoteFiles.take(8).forEach { Text(it, style = MaterialTheme.typography.bodyMedium) }
            }
        }
    }
}

@Composable
private fun ConsoleScreen(state: CncUiState, viewModel: CncViewModel) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Checkbox(checked = state.hideStatusReports, onCheckedChange = viewModel::setHideStatusReports)
            Text("Durum raporlarını gizle", modifier = Modifier.weight(1f))
            TextButton(onClick = viewModel::clearConsole) {
                Icon(Icons.Default.Clear, contentDescription = null)
                Spacer(Modifier.width(4.dp))
                Text("Temizle")
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedTextField(
                value = state.commandEntry,
                onValueChange = viewModel::setCommandEntry,
                modifier = Modifier.weight(1f),
                label = { Text("Komut") },
                singleLine = true,
            )
            Button(onClick = viewModel::sendManualCommand, modifier = Modifier.align(Alignment.CenterVertically)) {
                Icon(Icons.Default.Send, contentDescription = null)
            }
        }
        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(8.dp))
                .padding(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            items(state.console) { entry ->
                val color = when (entry.type) {
                    ConsoleType.TX -> Color(0xFF1565C0)
                    ConsoleType.RX -> Color(0xFF2E7D32)
                    ConsoleType.INFO -> MaterialTheme.colorScheme.onSurface
                    ConsoleType.WARN -> Color(0xFF8A5A00)
                    ConsoleType.ERROR -> MaterialTheme.colorScheme.error
                }
                Text(
                    text = "${entry.time} ${entry.type.name}: ${entry.text}",
                    color = color,
                    style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                )
            }
        }
    }
}

@Composable
private fun ConnectionHero(state: CncUiState) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(32.dp),
        color = MaterialTheme.colorScheme.primary,
        shadowElevation = 12.dp,
    ) {
        Column(
            modifier = Modifier.padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Surface(shape = CircleShape, color = Color.White.copy(alpha = 0.16f)) {
                    Icon(
                        Icons.Default.Cable,
                        contentDescription = null,
                        modifier = Modifier.padding(9.dp),
                        tint = Color.White,
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        if (state.connected) "Makine bağlı" else "Bağlantı bekleniyor",
                        color = Color.White,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        state.connectionDescription,
                        color = Color.White.copy(alpha = 0.78f),
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Surface(shape = RoundedCornerShape(8.dp), color = Color.White.copy(alpha = 0.14f)) {
                    Text(
                        state.profile.label,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                        color = Color.White,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                HeroMetric("Signal", if (state.connected) "98%" else "--", Modifier.weight(1f))
                HeroMetric("Latency", if (state.connected) "12 ms" else "--", Modifier.weight(1f))
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Surface(shape = RoundedCornerShape(10.dp), color = Color.White.copy(alpha = 0.12f)) {
                    Icon(
                        Icons.Default.Terminal,
                        contentDescription = null,
                        modifier = Modifier.padding(8.dp),
                        tint = Color(0xFF99F6E4),
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text("Controller", color = Color(0xFFB2F5EA), style = MaterialTheme.typography.labelSmall)
                    Text(
                        "${state.profile.label} • ${state.connectionMode.label}",
                        color = Color.White,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

@Composable
private fun GaugeOverview(state: CncUiState) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        GaugeCard(
            label = "Spindle",
            value = state.status.spindle.toFloat(),
            max = state.machineProfile.spindleMax.coerceAtLeast(1).toFloat(),
            display = state.status.spindle.toString(),
            unit = "RPM",
            accent = MaterialTheme.colorScheme.primary,
            modifier = Modifier.weight(1f),
        )
        GaugeCard(
            label = "Feed",
            value = state.status.feed.toFloat(),
            max = 6000f,
            display = state.status.feed.toString(),
            unit = "mm/min",
            accent = MaterialTheme.colorScheme.tertiary,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun GaugeCard(
    label: String,
    value: Float,
    max: Float,
    display: String,
    unit: String,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    val progress = (value / max).coerceIn(0f, 1f)
    Surface(
        modifier = modifier.height(154.dp),
        shape = RoundedCornerShape(24.dp),
        color = Color.White,
        shadowElevation = 1.dp,
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Canvas(modifier = Modifier.size(86.dp)) {
                val stroke = 7.dp.toPx()
                val diameter = size.minDimension - stroke
                val topLeft = Offset((size.width - diameter) / 2f, (size.height - diameter) / 2f)
                drawArc(
                    color = Color(0xFFE2E8F0),
                    startAngle = -90f,
                    sweepAngle = 360f,
                    useCenter = false,
                    topLeft = topLeft,
                    size = Size(diameter, diameter),
                    style = Stroke(stroke, cap = StrokeCap.Round),
                )
                drawArc(
                    color = accent,
                    startAngle = -90f,
                    sweepAngle = 360f * progress,
                    useCenter = false,
                    topLeft = topLeft,
                    size = Size(diameter, diameter),
                    style = Stroke(stroke, cap = StrokeCap.Round),
                )
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(display, color = Color(0xFF1E293B), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Black)
                Text(unit, color = Color(0xFF94A3B8), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                Text(label, color = Color(0xFF64748B), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun DarkDroPanel(state: CncUiState, viewModel: CncViewModel) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        color = Color(0xFF0F172A),
        shadowElevation = 8.dp,
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Work Coordinates (WCS)",
                    color = Color(0xFF64748B),
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Black,
                    modifier = Modifier.weight(1f),
                )
                Surface(shape = RoundedCornerShape(6.dp), color = MaterialTheme.colorScheme.primary) {
                    Text(
                        "G54",
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        color = Color.White,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
            DarkAxisRow("X", state.status.workPosition.display('X'), { viewModel.zeroAxis('X') })
            DarkAxisRow("Y", state.status.workPosition.display('Y'), { viewModel.zeroAxis('Y') })
            DarkAxisRow("Z", state.status.workPosition.display('Z'), { viewModel.zeroAxis('Z') })
            Button(onClick = viewModel::zeroAll, modifier = Modifier.fillMaxWidth()) {
                Text("Zero XYZ")
            }
        }
    }
}

@Composable
private fun DarkAxisRow(axis: String, value: String, onZero: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(axis, color = Color(0xFF64748B), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Black)
        Text(
            value,
            color = Color.White,
            style = MaterialTheme.typography.headlineMedium,
            fontFamily = FontFamily.Monospace,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.weight(1f),
        )
        Surface(shape = RoundedCornerShape(10.dp), color = Color.White.copy(alpha = 0.06f), onClick = onZero) {
            Text(
                "ZERO",
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 10.dp),
                color = Color.White.copy(alpha = 0.55f),
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun JobStatusCard(state: CncUiState) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        color = Color.White,
        shadowElevation = 1.dp,
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.Top) {
                Column(modifier = Modifier.weight(1f)) {
                    Text("Current Job", color = Color(0xFF94A3B8), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                    Text(
                        if (state.gcodeText.isBlank()) "No G-code loaded" else "Mobile_Job.nc",
                        color = Color(0xFF1E293B),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "${state.gcodeStats.lineCount} lines • ${state.gcodeStats.motionCount} motions",
                        color = Color(0xFF94A3B8),
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
                Surface(
                    shape = RoundedCornerShape(6.dp),
                    color = if (state.streaming) Color(0xFFFFEDD5) else Color(0xFFF1F5F9),
                ) {
                    Text(
                        if (state.streaming) "RUNNING" else "READY",
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        color = if (state.streaming) Color(0xFFEA580C) else Color(0xFF64748B),
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Black,
                    )
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                    Text("Progress", color = Color(0xFF94A3B8), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                    Text("${(state.streamProgress * 100).toInt()}%", color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Black)
                }
                LinearProgressIndicator(progress = { state.streamProgress }, modifier = Modifier.fillMaxWidth().height(8.dp))
            }
        }
    }
}

@Composable
private fun MachineHero(state: CncUiState) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.primary,
        shadowElevation = 2.dp,
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatusDot(state.status.normalizedState)
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        state.status.normalizedState.uppercase(Locale.getDefault()),
                        color = Color.White,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        "${state.profile.label} • ${state.connectionDescription}",
                        color = Color.White.copy(alpha = 0.78f),
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (state.status.limitPins.isNotBlank()) {
                    Surface(shape = RoundedCornerShape(8.dp), color = MaterialTheme.colorScheme.error) {
                        Text(
                            "LIMIT ${state.status.limitPins}",
                            modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
                            color = Color.White,
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                MiniGauge(
                    label = "Feed",
                    value = state.status.feed.toFloat(),
                    max = 6000f,
                    display = "${state.status.feed}",
                    unit = "mm/min",
                    color = Color(0xFF63D4C7),
                    modifier = Modifier.weight(1f),
                )
                MiniGauge(
                    label = "Spindle",
                    value = state.status.spindle.toFloat(),
                    max = state.machineProfile.spindleMax.coerceAtLeast(1).toFloat(),
                    display = "${state.status.spindle}",
                    unit = "RPM",
                    color = Color(0xFFF2C14E),
                    modifier = Modifier.weight(1f),
                )
            }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                HeroMetric("Feed", "${state.status.feedOverride}%", Modifier.weight(1f))
                HeroMetric("Rapid", "${state.status.rapidOverride}%", Modifier.weight(1f))
                HeroMetric("Spindle", "${state.status.spindleOverride}%", Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun HeroMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(8.dp),
        color = Color.White.copy(alpha = 0.12f),
    ) {
        Column(modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp)) {
            Text(label, color = Color.White.copy(alpha = 0.72f), style = MaterialTheme.typography.labelSmall)
            Text(
                value,
                color = Color.White,
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun MiniGauge(
    label: String,
    value: Float,
    max: Float,
    display: String,
    unit: String,
    color: Color,
    modifier: Modifier = Modifier,
) {
    val progress = (value / max).coerceIn(0f, 1f)
    Surface(
        modifier = modifier.height(122.dp),
        shape = RoundedCornerShape(10.dp),
        color = Color.White.copy(alpha = 0.12f),
    ) {
        Column(
            modifier = Modifier.padding(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(label, color = Color.White.copy(alpha = 0.76f), style = MaterialTheme.typography.labelLarge)
            Canvas(modifier = Modifier.size(68.dp)) {
                val stroke = 9.dp.toPx()
                val diameter = size.minDimension - stroke
                val topLeft = Offset((size.width - diameter) / 2f, (size.height - diameter) / 2f)
                drawArc(
                    color = Color.White.copy(alpha = 0.18f),
                    startAngle = 135f,
                    sweepAngle = 270f,
                    useCenter = false,
                    topLeft = topLeft,
                    size = Size(diameter, diameter),
                    style = Stroke(width = stroke, cap = StrokeCap.Round),
                )
                drawArc(
                    color = color,
                    startAngle = 135f,
                    sweepAngle = 270f * progress,
                    useCenter = false,
                    topLeft = topLeft,
                    size = Size(diameter, diameter),
                    style = Stroke(width = stroke, cap = StrokeCap.Round),
                )
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(display, color = Color.White, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Black)
                Text(unit, color = Color.White.copy(alpha = 0.72f), style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun Panel(title: String, icon: ImageVector? = null, content: @Composable ColumnScope.() -> Unit) {
    ElevatedCard(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.elevatedCardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.elevatedCardElevation(defaultElevation = 1.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (icon != null) {
                    Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.surfaceVariant) {
                        Icon(
                            icon,
                            contentDescription = null,
                            modifier = Modifier
                                .size(34.dp)
                                .padding(8.dp),
                            tint = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }
            content()
        }
    }
}

@Composable
private fun TextFieldLine(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    keyboardType: KeyboardType = KeyboardType.Text,
    password: Boolean = false,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        visualTransformation = if (password) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun <T> SelectField(
    label: String,
    value: String,
    options: List<T>,
    optionLabel: (T) -> String,
    onSelect: (T) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    Column {
        Text(label, style = MaterialTheme.typography.labelLarge)
        Box {
            OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth()) {
                Text(value, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Icon(Icons.Default.KeyboardArrowDown, contentDescription = null)
            }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                options.forEach { option ->
                    DropdownMenuItem(
                        text = { Text(optionLabel(option)) },
                        onClick = {
                            expanded = false
                            onSelect(option)
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun StatusDot(state: String) {
    val color = when (state) {
        "Idle" -> Color(0xFF2E7D32)
        "Run" -> Color(0xFF1565C0)
        "Jog" -> Color(0xFF00838F)
        "Hold" -> Color(0xFFF2A51A)
        "Homing" -> Color(0xFF00796B)
        "Alarm", "Door" -> Color(0xFFC62828)
        else -> Color(0xFF7B8390)
    }
    Box(
        modifier = Modifier
            .padding(horizontal = 10.dp)
            .size(14.dp)
            .background(color, CircleShape)
    )
}

@Composable
private fun AxisRow(axis: String, work: String, machine: String, onZero: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(axis, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Black, modifier = Modifier.width(24.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text("W $work", style = MaterialTheme.typography.titleMedium, fontFamily = FontFamily.Monospace)
            Text("M $machine", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        OutlinedButton(onClick = onZero) { Text("0") }
    }
}

@Composable
private fun JogPad(viewModel: CncViewModel) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                JogEmptyCell()
                JogButton(
                    axis = "Y+",
                    label = "Y ileri",
                    icon = Icons.Default.KeyboardArrowUp,
                    onClick = { viewModel.jog('Y', 1) },
                    modifier = Modifier.weight(1f),
                )
                JogEmptyCell()
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                JogButton(
                    axis = "X-",
                    label = "X sol",
                    icon = Icons.Default.KeyboardArrowLeft,
                    onClick = { viewModel.jog('X', -1) },
                    modifier = Modifier.weight(1f),
                )
                JogCenterCell()
                JogButton(
                    axis = "X+",
                    label = "X sağ",
                    icon = Icons.Default.KeyboardArrowRight,
                    onClick = { viewModel.jog('X', 1) },
                    modifier = Modifier.weight(1f),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                JogEmptyCell()
                JogButton(
                    axis = "Y-",
                    label = "Y geri",
                    icon = Icons.Default.KeyboardArrowDown,
                    onClick = { viewModel.jog('Y', -1) },
                    modifier = Modifier.weight(1f),
                )
                JogEmptyCell()
            }
        }

        Column(
            modifier = Modifier.width(96.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Z ekseni", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
            JogButton(
                axis = "Z+",
                label = "Yukarı",
                icon = Icons.Default.KeyboardArrowUp,
                onClick = { viewModel.jog('Z', 1) },
                modifier = Modifier.fillMaxWidth(),
                primary = false,
            )
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(42.dp),
                shape = RoundedCornerShape(8.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text("Z", fontWeight = FontWeight.Black, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            JogButton(
                axis = "Z-",
                label = "Aşağı",
                icon = Icons.Default.KeyboardArrowDown,
                onClick = { viewModel.jog('Z', -1) },
                modifier = Modifier.fillMaxWidth(),
                primary = false,
            )
        }
    }
}

@Composable
private fun JogButton(
    axis: String,
    label: String,
    icon: ImageVector,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    primary: Boolean = true,
) {
    val colors = if (primary) {
        ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
    } else {
        ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.tertiary,
            contentColor = MaterialTheme.colorScheme.onTertiary,
        )
    }
    Button(
        onClick = onClick,
        modifier = modifier.height(72.dp),
        shape = RoundedCornerShape(8.dp),
        colors = colors,
        contentPadding = ButtonDefaults.ContentPadding,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(icon, contentDescription = axis, modifier = Modifier.size(24.dp))
            Text(axis, fontWeight = FontWeight.Black, maxLines = 1)
            Text(label, style = MaterialTheme.typography.labelSmall, maxLines = 1)
        }
    }
}

@Composable
private fun RowScope.JogEmptyCell() {
    Spacer(
        modifier = Modifier
            .weight(1f)
            .height(72.dp)
    )
}

@Composable
private fun RowScope.JogCenterCell() {
    Surface(
        modifier = Modifier
            .weight(1f)
            .height(72.dp),
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
    ) {
        Column(
            modifier = Modifier.padding(6.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text("XY", fontWeight = FontWeight.Black)
            Text("Jog", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private data class ActionSpec(val label: String, val icon: ImageVector, val onClick: () -> Unit)

@Composable
private fun ActionGrid(actions: List<ActionSpec>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        actions.chunked(2).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                row.forEach { action ->
                    OutlinedButton(onClick = action.onClick, modifier = Modifier.weight(1f)) {
                        Icon(action.icon, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text(action.label, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun SliderRow(
    label: String,
    value: Float,
    range: ClosedFloatingPointRange<Float>,
    display: String,
    onChange: (Float) -> Unit,
) {
    Column {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(label, style = MaterialTheme.typography.labelLarge)
            Text(display, fontWeight = FontWeight.SemiBold)
        }
        Slider(value = value.coerceIn(range.start, range.endInclusive), onValueChange = onChange, valueRange = range)
    }
}

@Composable
private fun GCodeStatsView(stats: GCodeStats) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            AssistChip(onClick = {}, label = { Text("${stats.lineCount} satır") })
            AssistChip(onClick = {}, label = { Text("${stats.motionCount} hareket") })
        }
        if (stats.hasBounds) {
            InfoRow("X", "${stats.minX!!.format()} .. ${stats.maxX!!.format()} mm")
            InfoRow("Y", "${stats.minY!!.format()} .. ${stats.maxY!!.format()} mm")
            GCodePreview(stats)
        }
    }
}

@Composable
private fun GCodePreview(stats: GCodeStats) {
    Canvas(
        modifier = Modifier
            .fillMaxWidth()
            .height(150.dp)
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp))
            .padding(8.dp)
    ) {
        val minX = stats.minX ?: return@Canvas
        val maxX = stats.maxX ?: return@Canvas
        val minY = stats.minY ?: return@Canvas
        val maxY = stats.maxY ?: return@Canvas
        val width = (maxX - minX).coerceAtLeast(1.0)
        val height = (maxY - minY).coerceAtLeast(1.0)
        val scale = minOf(size.width / width.toFloat(), size.height / height.toFloat()) * 0.82f
        val drawWidth = width.toFloat() * scale
        val drawHeight = height.toFloat() * scale
        val left = (size.width - drawWidth) / 2f
        val top = (size.height - drawHeight) / 2f
        val path = Path().apply {
            moveTo(left, top)
            lineTo(left + drawWidth, top)
            lineTo(left + drawWidth, top + drawHeight)
            lineTo(left, top + drawHeight)
            close()
        }
        drawPath(path, color = Color(0xFF176B62), style = Stroke(width = 3f))
        drawLine(
            Color(0xFF8A5A2B),
            Offset(left, top + drawHeight),
            Offset(left + drawWidth, top + drawHeight),
            strokeWidth = 2f,
        )
    }
}

private fun Double.format(): String = String.format(Locale.US, "%.3f", this)

package com.flatcam.cnc.domain

import java.util.Locale

data class AxisPosition(
    val x: Double = 0.0,
    val y: Double = 0.0,
    val z: Double = 0.0,
) {
    fun display(axis: Char): String {
        val value = when (axis.uppercaseChar()) {
            'X' -> x
            'Y' -> y
            else -> z
        }
        return String.format(Locale.US, "%.3f", value)
    }
}

data class CncStatus(
    val state: String = "Offline",
    val workPosition: AxisPosition = AxisPosition(),
    val machinePosition: AxisPosition = AxisPosition(),
    val feed: Int = 0,
    val spindle: Int = 0,
    val feedOverride: Int = 100,
    val rapidOverride: Int = 100,
    val spindleOverride: Int = 100,
    val limitPins: String = "",
) {
    val normalizedState: String
        get() = normalizeState(state)
}

private val axisPattern = Regex("""([XYZ]):\s*(-?\d+(?:\.\d+)?)""")

fun CncStatus.updatedByControllerLine(line: String): CncStatus? {
    val trimmed = line.trim()
    if (trimmed.startsWith("<") && trimmed.endsWith(">")) {
        val parts = trimmed.substring(1, trimmed.length - 1).split("|")
        if (parts.isEmpty()) return null

        var next = copy(state = normalizeState(parts.first()))
        val values = parts.drop(1).mapNotNull {
            val idx = it.indexOf(':')
            if (idx < 0) null else it.substring(0, idx) to it.substring(idx + 1)
        }.toMap()

        values["WPos"]?.parsePosition()?.let { next = next.copy(workPosition = it) }
        values["MPos"]?.parsePosition()?.let { next = next.copy(machinePosition = it) }
        if (values["WPos"] == null && values["MPos"] != null && values["WCO"] != null) {
            val machine = values.getValue("MPos").parsePosition()
            val offset = values.getValue("WCO").parsePosition()
            if (machine != null && offset != null) {
                next = next.copy(
                    workPosition = AxisPosition(
                        x = machine.x - offset.x,
                        y = machine.y - offset.y,
                        z = machine.z - offset.z,
                    ),
                    machinePosition = machine,
                )
            }
        }

        values["FS"]?.split(",")?.let { fs ->
            next = next.copy(
                feed = fs.getOrNull(0).toIntValue(),
                spindle = fs.getOrNull(1).toIntValue(),
            )
        }
        values["Ov"]?.split(",")?.let { ov ->
            next = next.copy(
                feedOverride = ov.getOrNull(0).toIntValue(100),
                rapidOverride = ov.getOrNull(1).toIntValue(100),
                spindleOverride = ov.getOrNull(2).toIntValue(100),
            )
        }
        values["Pn"]?.let { pins ->
            next = next.copy(limitPins = pins.uppercase(Locale.US).filter { it in "XYZ" })
        }
        return next
    }

    if ("X:" in trimmed && "Y:" in trimmed && "Z:" in trimmed) {
        val values = axisPattern.findAll(trimmed).associate { it.groupValues[1] to it.groupValues[2] }
        if (values.isNotEmpty()) {
            return copy(
                state = "Idle",
                workPosition = AxisPosition(
                    x = values["X"].toDoubleValue(),
                    y = values["Y"].toDoubleValue(),
                    z = values["Z"].toDoubleValue(),
                )
            )
        }
    }

    return null
}

fun normalizeState(value: String): String {
    val base = value.trim().substringBefore(":").lowercase(Locale.US)
    return when (base) {
        "home", "homing" -> "Homing"
        "idle" -> "Idle"
        "run" -> "Run"
        "jog" -> "Jog"
        "hold" -> "Hold"
        "alarm" -> "Alarm"
        "door" -> "Door"
        "check" -> "Check"
        "sleep" -> "Sleep"
        "offline" -> "Offline"
        else -> value.ifBlank { "Idle" }
    }
}

fun parseSdFileLine(line: String, isCollecting: Boolean): Pair<String?, Boolean> {
    val trimmed = line.trim()
    val lower = trimmed.lowercase(Locale.US)
    if (lower == "begin file list") return null to true
    if (lower == "end file list") return null to false
    if (trimmed.startsWith("[FILE:")) {
        val name = trimmed.substringAfter("[FILE:").substringBefore("|").trimEnd(']')
        return name to isCollecting
    }
    if (isCollecting && trimmed.isNotBlank() && !lower.startsWith("ok") && !lower.startsWith("echo:")) {
        return trimmed.split(Regex("\\s+")).firstOrNull() to true
    }
    return null to isCollecting
}

fun isControllerAck(line: String): Boolean {
    val lower = line.trim().lowercase(Locale.US)
    return lower == "ok" || lower.startsWith("error") || lower.startsWith("alarm")
}

private fun String?.toDoubleValue(default: Double = 0.0): Double =
    this?.toDoubleOrNull() ?: default

private fun String?.toIntValue(default: Int = 0): Int =
    this?.substringBefore(".")?.toIntOrNull() ?: this?.toDoubleOrNull()?.toInt() ?: default

private fun String.parsePosition(): AxisPosition? {
    val parts = split(",")
    if (parts.size < 3) return null
    return AxisPosition(parts[0].toDoubleValue(), parts[1].toDoubleValue(), parts[2].toDoubleValue())
}

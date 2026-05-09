package com.flatcam.cnc.domain

data class CncCommand(
    val lines: List<String> = emptyList(),
    val raw: ByteArray? = null,
) {
    companion object {
        fun line(value: String) = CncCommand(lines = value.lines().filter { it.isNotBlank() })
        fun raw(vararg values: Int) = CncCommand(raw = values.map { it.toByte() }.toByteArray())
    }
}

enum class CncProfile(val label: String) {
    FLUIDNC("FluidNC"),
    GRBL("GRBL"),
    MARLIN("Marlin"),
    SMOOTHIE("Smoothieware"),
    GENERIC("Generic G-code");

    fun command(key: String): CncCommand? = when (this) {
        FLUIDNC, GRBL -> when (key) {
            "info" -> CncCommand.line("\$I")
            "web_info" -> CncCommand.line("[ESP800]")
            "config" -> CncCommand.line("\$Config/Dump")
            "home" -> CncCommand.line("\$H")
            "unlock" -> CncCommand.line("\$X")
            "reset" -> CncCommand.raw(0x18)
            "hold" -> CncCommand.raw(0x21)
            "resume" -> CncCommand.raw(0x7e)
            "status" -> CncCommand.line("?")
            "status_raw" -> CncCommand.raw(0x3f)
            "zero_all" -> CncCommand.line("G10 L20 P1 X0 Y0 Z0")
            "sd_list" -> CncCommand.line("\$SD/List")
            "feed_plus" -> CncCommand.raw(0x91)
            "feed_minus" -> CncCommand.raw(0x92)
            "feed_reset" -> CncCommand.raw(0x90)
            "spindle_plus" -> CncCommand.raw(0x9a)
            "spindle_minus" -> CncCommand.raw(0x9b)
            "spindle_reset" -> CncCommand.raw(0x99)
            "spindle_stop" -> CncCommand.line("M5")
            "laser_on" -> CncCommand.line("M3 S100")
            "laser_off" -> CncCommand.line("M5")
            else -> null
        }
        MARLIN -> when (key) {
            "info" -> CncCommand.line("M115")
            "config" -> CncCommand.line("M503")
            "home" -> CncCommand.line("G28")
            "unlock", "reset" -> CncCommand.line("M999")
            "hold" -> CncCommand.line("M0")
            "resume" -> CncCommand.line("M24")
            "status" -> CncCommand.line("M114")
            "zero_all" -> CncCommand.line("G92 X0 Y0 Z0")
            "sd_list" -> CncCommand.line("M20")
            "feed_plus" -> CncCommand.line("M220 S110")
            "feed_minus" -> CncCommand.line("M220 S90")
            "feed_reset" -> CncCommand.line("M220 S100")
            "spindle_stop" -> CncCommand.line("M5")
            "laser_on" -> CncCommand.line("M3 S100")
            "laser_off" -> CncCommand.line("M5")
            else -> null
        }
        SMOOTHIE -> when (key) {
            "info" -> CncCommand.line("version")
            "config" -> CncCommand.line("config-get sd")
            "home" -> CncCommand.line("G28")
            "unlock" -> CncCommand.line("M999")
            "reset" -> CncCommand.raw(0x18)
            "hold" -> CncCommand.line("M600")
            "resume" -> CncCommand.line("M601")
            "status" -> CncCommand.line("?")
            "status_raw" -> CncCommand.raw(0x3f)
            "zero_all" -> CncCommand.line("G92 X0 Y0 Z0")
            "spindle_stop" -> CncCommand.line("M5")
            "laser_on" -> CncCommand.line("M3 S100")
            "laser_off" -> CncCommand.line("M5")
            else -> null
        }
        GENERIC -> when (key) {
            "home" -> CncCommand.line("G28")
            "hold" -> CncCommand.line("M0")
            "zero_all" -> CncCommand.line("G92 X0 Y0 Z0")
            "spindle_stop" -> CncCommand.line("M5")
            "laser_on" -> CncCommand.line("M3 S100")
            "laser_off" -> CncCommand.line("M5")
            else -> null
        }
    }

    fun zeroAxis(axis: Char): CncCommand {
        val upper = axis.uppercaseChar()
        return when (this) {
            FLUIDNC, GRBL -> CncCommand.line("G10 L20 P1 ${upper}0")
            else -> CncCommand.line("G92 ${upper}0")
        }
    }

    fun jog(axis: Char, distance: Double, feed: Int): CncCommand {
        val upper = axis.uppercaseChar()
        val value = "%.4f".format(java.util.Locale.US, distance)
        return when (this) {
            FLUIDNC, GRBL -> CncCommand.line("\$J=G91 G21 $upper$value F$feed")
            else -> CncCommand.line("G91\nG0 $upper$value F$feed\nG90")
        }
    }

    fun feedOverride(percent: Int): CncCommand = CncCommand.line("M220 S$percent")

    fun spindleOverride(percent: Int): CncCommand = CncCommand.line("M221 S$percent")

    fun spindleRpm(rpm: Int): CncCommand = CncCommand.line("M3 S$rpm")

    fun runSd(fileName: String): CncCommand? = when (this) {
        FLUIDNC, GRBL -> CncCommand.line("\$SD/Run=$fileName")
        MARLIN -> CncCommand.line("M23 $fileName\nM24")
        else -> null
    }
}

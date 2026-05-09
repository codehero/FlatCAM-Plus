package com.flatcam.cnc.domain

data class GCodeStats(
    val lineCount: Int = 0,
    val motionCount: Int = 0,
    val minX: Double? = null,
    val maxX: Double? = null,
    val minY: Double? = null,
    val maxY: Double? = null,
) {
    val hasBounds: Boolean = minX != null && maxX != null && minY != null && maxY != null
}

private val parenthesisComment = Regex("""\([^)]*\)""")
private val wordPattern = Regex("""([XYZ])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))""", RegexOption.IGNORE_CASE)

fun cleanGCodeLine(line: String): String {
    val noParenthesis = parenthesisComment.replace(line, "")
    return noParenthesis.substringBefore(";").trim()
}

fun normalizedGCodeLines(text: String): List<String> =
    text.lines().map(::cleanGCodeLine).filter { it.isNotBlank() }

fun calculateGCodeStats(text: String): GCodeStats {
    var minX: Double? = null
    var maxX: Double? = null
    var minY: Double? = null
    var maxY: Double? = null
    var motion = 0
    val lines = normalizedGCodeLines(text)

    for (line in lines) {
        val upper = line.uppercase()
        if (upper.contains("G0") || upper.contains("G1") || upper.contains("G2") || upper.contains("G3")) {
            motion += 1
        }
        for (match in wordPattern.findAll(line)) {
            val axis = match.groupValues[1].uppercase()
            val value = match.groupValues[2].toDoubleOrNull() ?: continue
            if (axis == "X") {
                minX = minOf(minX ?: value, value)
                maxX = maxOf(maxX ?: value, value)
            }
            if (axis == "Y") {
                minY = minOf(minY ?: value, value)
                maxY = maxOf(maxY ?: value, value)
            }
        }
    }

    return GCodeStats(
        lineCount = lines.size,
        motionCount = motion,
        minX = minX,
        maxX = maxX,
        minY = minY,
        maxY = maxY,
    )
}

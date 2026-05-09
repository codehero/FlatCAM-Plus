package com.flatcam.cnc.domain

data class MachineProfile(
    val name: String = "Default CNC",
    val safeZ: Double = 5.0,
    val jogFeed: Int = 1000,
    val probeFeed: Int = 100,
    val spindleMax: Int = 12000,
    val travelX: Double = 300.0,
    val travelY: Double = 300.0,
    val travelZ: Double = 80.0,
)

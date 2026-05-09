package com.flatcam.cnc.transport

enum class ConnectionMode(val label: String) {
    HTTP("FluidNC HTTP"),
    TCP("TCP/Telnet"),
    USB_SERIAL("USB Serial"),
}

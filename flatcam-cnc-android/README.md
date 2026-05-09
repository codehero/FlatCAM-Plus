# FlatCAM CNC Android (Beta)

Native Android CNC control companion app for FlatCAM Plus. This module is currently **beta** and is intended for testing mobile controller sessions alongside the desktop CNC workflow.

## Features

- FluidNC HTTP, TCP/Telnet, and Android USB Serial connection modes.
- Controller profile selection for GRBL, FluidNC, Marlin, Smoothieware, and generic G-code controllers.
- Connection testing before opening a live session.
- Live status polling with WPos/MPos DRO, feed, spindle, override, and controller state display.
- Home, unlock, reset, hold, resume, info, zero, and jog commands.
- Feed override, spindle override, spindle RPM, spindle stop, and laser toggle controls.
- Local G-code file open, sample program loading, line-by-line streaming, pause, and stop.
- SD file listing and selected SD file start support where the controller transport supports it.
- Manual command console with TX/RX logs.
- Android USB permission flow for serial devices.

## Build

```powershell
cd C:\Users\sadri\Desktop\flatfixed\flatcam-cnc-android
.\gradlew.bat assembleDebug
```

Debug APK:

```text
app\build\outputs\apk\debug\app-debug.apk
```

Android USB Serial requires a device with USB host support. The app asks Android for USB device permission on the first serial connection.

## Notes

- This app is beta software.
- Do not rely on it for unattended machine operation.
- Always verify controller motion and work zero before streaming a job.

@echo off
setlocal

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\windows\run_installer_generator.ps1" -Target x32 %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Derleme basarisiz oldu. Hata kodu: %EXIT_CODE%
    echo Detaylar icin build\logs klasorundeki son log dosyasini kontrol edin.
    pause
)

exit /b %EXIT_CODE%

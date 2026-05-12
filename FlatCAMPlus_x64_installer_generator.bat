@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

:: ============================================================
::  FlatCAM Plus - Versiyon Girişli Release Builder (x64)
::  Calistirin, versiyon girin, bekleyin.
:: ============================================================

echo.
echo  =========================================================
echo   FlatCAM Plus ^| x64 Release Builder
echo  =========================================================
echo.

:: ---- Mevcut versiyonu appVersion.py'den oku ----
for /f "usebackq" %%V in (`powershell -NoProfile -Command ^
    "(Select-String -Path '%~dp0appVersion.py' -Pattern 'APP_VERSION\s*=\s*[\""]([^\""]+)[\""]').Matches[0].Groups[1].Value 2>$null"`) do (
    set "CURRENT_VERSION=%%V"
)
if not defined CURRENT_VERSION set "CURRENT_VERSION=bilinmiyor"

echo   Mevcut versiyon : !CURRENT_VERSION!
echo.

:: ---- Yeni versiyon girişi ----
:ASK_VERSION
set "NEW_VERSION="
set /p "NEW_VERSION=  Yeni versiyon girin (bos birakip Enter = mevcut kalsın): "

if "!NEW_VERSION!"=="" (
    set "NEW_VERSION=!CURRENT_VERSION!"
    echo   [INFO] Mevcut versiyon kullanılıyor: !NEW_VERSION!
    goto CONFIRM_STEP
)

    :: Format doğrulama: X.Y.Z (PowerShell ile - findstr regex güvenilmez)
    powershell -NoProfile -Command "if ('!NEW_VERSION!' -match '^[0-9]+\.[0-9]+\.[0-9]+$') { exit 0 } else { exit 1 }" >nul 2>&1
    if errorlevel 1 (
        echo   [UYARI] Gecersiz format! Ornek: 1.2.3
        goto ASK_VERSION
    )

:CONFIRM_STEP
echo.

:: ---- Release tarihi ----
for /f "usebackq" %%D in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy/MM/dd'"`) do (
    set "RELEASE_DATE=%%D"
)

echo   Yeni versiyon   : !NEW_VERSION!
echo   Release tarihi  : !RELEASE_DATE!
echo.
set /p "CONFIRM=  Onaylıyor musunuz? (E/H): "
if /i "!CONFIRM!" neq "E" (
    echo   Iptal edildi.
    pause
    exit /b 0
)

:: ---- 1/3: Versiyon dosyalarını güncelle (PS1 yardımcısı ile) ----
echo.
echo  ---------------------------------------------------------
echo   1/3  Versiyon dosyaları güncelleniyor...
echo  ---------------------------------------------------------

powershell -NoProfile -ExecutionPolicy Bypass -File ^
    "%~dp0packaging\windows\update_version.ps1" ^
    -Version "!NEW_VERSION!" ^
    -RootDir "%~dp0."

if errorlevel 1 (
    echo.
    echo   [HATA] Versiyon guncelleme basarisiz!
    pause
    exit /b 1
)

:: ---- 2/3: PyInstaller + Inno Setup (run_installer_generator.ps1) ----
echo.
echo  ---------------------------------------------------------
echo   2/3  Build basliyor (PyInstaller + Inno Setup)...
echo  ---------------------------------------------------------
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File ^
    "%~dp0packaging\windows\run_installer_generator.ps1" ^
    -Target x64 ^
    -Version "!NEW_VERSION!" ^
    %*

set "EXIT_CODE=%ERRORLEVEL%"

:: ---- Sonuç ----
echo.
echo  ---------------------------------------------------------
echo   3/3  Sonuc
echo  ---------------------------------------------------------

if "!EXIT_CODE!"=="0" (
    echo.
    echo   [BASARILI] Build tamamlandi!
    echo.
    echo   Versiyon  : !NEW_VERSION!
    echo   Cikti     : dist\installer\FlatCAMPlus-Setup-!NEW_VERSION!-x64.exe
    echo   Log       : build\logs\
    echo.
) else (
    echo.
    echo   [HATA] Build basarisiz! Hata kodu: !EXIT_CODE!
    echo   Log icin : build\logs\ klasorune bakin.
    echo.
)

pause
exit /b !EXIT_CODE!

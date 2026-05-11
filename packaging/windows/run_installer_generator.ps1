[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("x32", "x64")]
    [string] $Target,

    [string] $Version = "",
    [string] $PythonX86 = $env:PYTHON_X86,
    [string] $PythonX64 = $env:PYTHON_X64,
    [switch] $SkipPyInstaller,
    [switch] $SkipInstaller
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..\..")
$BuildScript = Join-Path $ScriptDir "build_windows_installer.ps1"
$LogDir = Join-Path $RootDir "build\logs"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
$LogPath = Join-Path $LogDir "FlatCAMPlus_${Target}_installer_generator_$Timestamp.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$exitCode = 0
Start-Transcript -Path $LogPath -Force | Out-Null

try {
    Write-Host "FlatCAM Plus $Target installer generator"
    Write-Host "Log dosyasi: $LogPath"
    Write-Host ""

    & $BuildScript `
        -Target $Target `
        -Version $Version `
        -PythonX86 $PythonX86 `
        -PythonX64 $PythonX64 `
        -SkipPyInstaller:$SkipPyInstaller `
        -SkipInstaller:$SkipInstaller

    if ($global:LASTEXITCODE -is [int]) {
        $exitCode = $global:LASTEXITCODE
    }

    if ($exitCode -ne 0) {
        throw "Derleme betigi hata kodu dondurdu: $exitCode"
    }

    Write-Host ""
    Write-Host "Derleme tamamlandi."
} catch {
    if ($exitCode -eq 0) {
        $exitCode = 1
    }

    Write-Host ""
    Write-Host "Derleme basarisiz oldu:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    Stop-Transcript | Out-Null
}

Write-Host ""
Write-Host "Log dosyasi: $LogPath"
exit $exitCode

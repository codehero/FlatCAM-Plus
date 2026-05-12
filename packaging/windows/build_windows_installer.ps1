[CmdletBinding()]
param(
    [string] $Version = "",
    [ValidateSet("both", "x86", "x32", "x64")]
    [string] $Target = "both",
    [string] $PythonX86 = $env:PYTHON_X86,
    [string] $PythonX64 = $env:PYTHON_X64,
    [switch] $SkipPyInstaller,
    [switch] $SkipInstaller
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..\..")
$InstallerScript = Join-Path $ScriptDir "FlatCAMPlus.iss"

Set-Location $RootDir

if ([string]::IsNullOrWhiteSpace($Version)) {
    $versionMatch = Select-String -Path (Join-Path $RootDir "appVersion.py") -Pattern 'APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($versionMatch) {
        $Version = $versionMatch.Matches[0].Groups[1].Value
    } else {
        $Version = "1.0.1"
    }
}

function ConvertTo-CanonicalArch {
    param([ValidateSet("x86", "x32", "x64")] [string] $Arch)

    if ($Arch -eq "x32") {
        return "x86"
    }
    return $Arch
}

function Get-InstallerArchLabel {
    param([ValidateSet("x86", "x32", "x64")] [string] $Arch)

    $canonicalArch = ConvertTo-CanonicalArch $Arch
    if ($canonicalArch -eq "x86") {
        return "x32"
    }
    return "x64"
}

function Invoke-PythonCommand {
    param(
        [string[]] $PythonCommand,
        [string[]] $Arguments
    )

    $exe = $PythonCommand[0]
    $prefixArgs = @()
    if ($PythonCommand.Count -gt 1) {
        $prefixArgs = $PythonCommand[1..($PythonCommand.Count - 1)]
    }

    & $exe @prefixArgs @Arguments
}

function Test-PythonBits {
    param(
        [string[]] $PythonCommand,
        [int] $ExpectedBits
    )

    try {
        $output = Invoke-PythonCommand -PythonCommand $PythonCommand -Arguments @("-c", "import struct; print(struct.calcsize('P') * 8)") 2>$null
        return ($LASTEXITCODE -eq 0 -and $output -and $output.Trim() -eq [string] $ExpectedBits)
    } catch {
        return $false
    }
}

function Resolve-PythonForArch {
    param([ValidateSet("x86", "x64")] [string] $Arch)

    $expectedBits = if ($Arch -eq "x86") { 32 } else { 64 }
    $explicitPath = if ($Arch -eq "x86") { $PythonX86 } else { $PythonX64 }
    $candidates = @()

    if (-not [string]::IsNullOrWhiteSpace($explicitPath)) {
        $candidates += ,@($explicitPath)
    }

    if ($Arch -eq "x86") {
        $candidates += ,@("py", "-3.11-32")
        $candidates += ,@("py", "-3-32")
        $candidates += ,@("python")
    } else {
        $candidates += ,@("py", "-3.11-64")
        $candidates += ,@("py", "-3-64")
        $candidates += ,@("python")
    }

    foreach ($candidate in $candidates) {
        if (Test-PythonBits $candidate $expectedBits) {
            return $candidate
        }
    }

    $hint = if ($Arch -eq "x86") {
        "32-bit Python kurun ve yolu PYTHON_X86 ortam degiskeniyle veya -PythonX86 parametresiyle verin."
    } else {
        "64-bit Python kurun ve yolu PYTHON_X64 ortam degiskeniyle veya -PythonX64 parametresiyle verin."
    }
    throw "$Arch icin $expectedBits-bit Python bulunamadi. $hint"
}

function Assert-PythonBuildModules {
    param(
        [string[]] $PythonCommand,
        [ValidateSet("x86", "x64")] [string] $Arch
    )

    $moduleNames = @("PyQt6", "vispy", "shapely", "rasterio", "OpenGL", "matplotlib", "ortools")
    $checkCode = "import importlib.util, sys; missing = [name for name in sys.argv[1:] if importlib.util.find_spec(name) is None]; print(', '.join(missing)); sys.exit(1 if missing else 0)"

    $checkArgs = @("-c", $checkCode) + $moduleNames
    $missing = Invoke-PythonCommand -PythonCommand $PythonCommand -Arguments $checkArgs 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "$Arch Python ortaminda eksik paketler var: $missing. Once su komutu calistirin: $($PythonCommand -join ' ') -m pip install -r requirements.txt"
    }
}

function Find-InnoCompiler {
    $candidates = New-Object System.Collections.Generic.List[string]

    if (-not [string]::IsNullOrWhiteSpace($env:ISCC_EXE)) {
        $candidates.Add($env:ISCC_EXE) | Out-Null
    }

    $installRoots = @(
        [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFilesX86),
        [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles),
        (Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) "Programs")
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

    foreach ($root in $installRoots) {
        $candidates.Add((Join-Path $root "Inno Setup 6\ISCC.exe")) | Out-Null
    }

    $registryPaths = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )

    Get-ItemProperty $registryPaths -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like "*Inno Setup*" } |
        ForEach-Object {
            if (-not [string]::IsNullOrWhiteSpace($_.InstallLocation)) {
                $candidates.Add((Join-Path $_.InstallLocation "ISCC.exe")) | Out-Null
            }

            if (-not [string]::IsNullOrWhiteSpace($_.DisplayIcon)) {
                $iconPath = $_.DisplayIcon.Trim('"')
                if ($iconPath -match "^(.*?\.exe)") {
                    $iconPath = $Matches[1]
                }

                $iconDir = Split-Path -Parent $iconPath -ErrorAction SilentlyContinue
                if (-not [string]::IsNullOrWhiteSpace($iconDir)) {
                    $candidates.Add((Join-Path $iconDir "ISCC.exe")) | Out-Null
                }
            }
        }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Inno Setup compiler bulunamadi. Kurulum: winget install JRSoftware.InnoSetup"
}

function Compile-Translations {
    $msgfmt = Get-Command "msgfmt.exe" -ErrorAction SilentlyContinue
    if (-not $msgfmt) {
        $msgfmt = Get-Command "msgfmt" -ErrorAction SilentlyContinue
    }

    if (-not $msgfmt) {
        Write-Warning "msgfmt bulunamadi; mevcut .mo dosyalari kullanilacak. Eksik ceviri varsa GNU gettext kurup tekrar calistirin."
        return
    }

    Get-ChildItem -Path (Join-Path $RootDir "locale") -Filter "strings.po" -Recurse | ForEach-Object {
        $output = Join-Path $_.DirectoryName "strings.mo"
        & $msgfmt.Source $_.FullName -o $output
    }
}

function New-PyInstallerDataArg {
    param(
        [string] $Source,
        [string] $Destination
    )

    $sourcePath = Join-Path $RootDir $Source
    return "$sourcePath;$Destination"
}

function New-PyInstallerBinaryArg {
    param(
        [string] $Source,
        [string] $Destination
    )

    return "$Source;$Destination"
}

function Resolve-PythonModulePath {
    param(
        [string[]] $PythonCommand,
        [string] $ModuleName
    )

    $resolveCode = "import importlib.util, pathlib, sys; spec = importlib.util.find_spec(sys.argv[1]); print(pathlib.Path(spec.origin).parent if spec and spec.origin else '')"
    $modulePath = Invoke-PythonCommand -PythonCommand $PythonCommand -Arguments @("-c", $resolveCode, $ModuleName)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($modulePath)) {
        throw "Python modulu bulunamadi: $ModuleName"
    }

    return $modulePath.Trim()
}

function Get-OrToolsBinaryArgs {
    param([string[]] $PythonCommand)

    $ortoolsPath = Resolve-PythonModulePath $PythonCommand "ortools"
    $libsPath = Join-Path $ortoolsPath ".libs"
    if (-not (Test-Path $libsPath)) {
        throw "OR-Tools DLL klasoru bulunamadi: $libsPath"
    }

    $binaryArgs = New-Object System.Collections.Generic.List[string]
    foreach ($dll in Get-ChildItem -Path $libsPath -Filter "*.dll") {
        $binaryArgs.Add("--add-binary") | Out-Null
        $binaryArgs.Add((New-PyInstallerBinaryArg $dll.FullName "ortools\.libs")) | Out-Null
    }

    return $binaryArgs.ToArray()
}

function New-AppIcon {
    param([string[]] $PythonCommand)

    $iconDir = Join-Path $RootDir "build\icons"
    $iconPath = Join-Path $iconDir "FlatCAMPlus.ico"
    $app32Path = Join-Path $RootDir "assets\resources\app32.png"
    $app48Path = Join-Path $RootDir "assets\resources\app48.png"

    New-Item -ItemType Directory -Force -Path $iconDir | Out-Null

    if (-not (Test-Path $app32Path)) {
        throw "Icon kaynak dosyasi bulunamadi: $app32Path"
    }
    if (-not (Test-Path $app48Path)) {
        throw "Icon kaynak dosyasi bulunamadi: $app48Path"
    }

    $app32Bytes = [System.IO.File]::ReadAllBytes($app32Path)
    $app48Bytes = [System.IO.File]::ReadAllBytes($app48Path)
    $stream = New-Object System.IO.MemoryStream
    $writer = New-Object System.IO.BinaryWriter($stream)

    try {
        $firstImageOffset = 6 + (16 * 2)
        $secondImageOffset = $firstImageOffset + $app32Bytes.Length

        $writer.Write([UInt16]0)
        $writer.Write([UInt16]1)
        $writer.Write([UInt16]2)

        $writer.Write([Byte]32)
        $writer.Write([Byte]32)
        $writer.Write([Byte]0)
        $writer.Write([Byte]0)
        $writer.Write([UInt16]1)
        $writer.Write([UInt16]32)
        $writer.Write([UInt32]$app32Bytes.Length)
        $writer.Write([UInt32]$firstImageOffset)

        $writer.Write([Byte]48)
        $writer.Write([Byte]48)
        $writer.Write([Byte]0)
        $writer.Write([Byte]0)
        $writer.Write([UInt16]1)
        $writer.Write([UInt16]32)
        $writer.Write([UInt32]$app48Bytes.Length)
        $writer.Write([UInt32]$secondImageOffset)

        $writer.Write($app32Bytes)
        $writer.Write($app48Bytes)
        [System.IO.File]::WriteAllBytes($iconPath, $stream.ToArray())
    } finally {
        $writer.Dispose()
        $stream.Dispose()
    }

    return $iconPath
}

function Build-PyInstallerTarget {
    param([ValidateSet("x86", "x64")] [string] $Arch)

    $python = Resolve-PythonForArch $Arch
    $archRoot = Join-Path $RootDir "dist\windows\$Arch"
    $workPath = Join-Path $RootDir "build\pyinstaller\$Arch"
    $specPath = Join-Path $RootDir "build\pyinstaller\$Arch"
    $appDistDir = Join-Path $archRoot "FlatCAMPlus"
    $exePath = Join-Path $appDistDir "FlatCAMPlus.exe"

    Invoke-PythonCommand -PythonCommand $python -Arguments @("-m", "PyInstaller", "--version") *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "$Arch Python ortaminda PyInstaller bulunamadi. Kurulum: $($python -join ' ') -m pip install pyinstaller"
    }

    Assert-PythonBuildModules $python $Arch
    $iconPath = New-AppIcon $python
    $ortoolsBinaryArgs = Get-OrToolsBinaryArgs $python

    $pyInstallerArgs = @(
        "-m", "PyInstaller", "flatcam.py",
        "--name", "FlatCAMPlus",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--icon", $iconPath,
        "--distpath", $archRoot,
        "--workpath", $workPath,
        "--specpath", $specPath,
        "--add-data", (New-PyInstallerDataArg "assets" "assets"),
        "--add-data", (New-PyInstallerDataArg "config" "config"),
        "--add-data", (New-PyInstallerDataArg "locale" "locale"),
        "--add-data", (New-PyInstallerDataArg "preprocessors" "preprocessors"),
        "--add-data", (New-PyInstallerDataArg "libs" "libs"),
        "--collect-submodules", "appCommon",
        "--collect-submodules", "appEditors",
        "--collect-submodules", "appGUI",
        "--collect-submodules", "appHandlers",
        "--collect-submodules", "appObjects",
        "--collect-submodules", "appParsers",
        "--collect-submodules", "appPlugins",
        "--collect-submodules", "tclCommands",
        "--collect-all", "PyQt6",
        "--collect-all", "vispy",
        "--collect-all", "shapely",
        "--collect-all", "rasterio",
        "--collect-all", "OpenGL",
        "--collect-all", "matplotlib",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PySide2",
        "--exclude-module", "PySide6",
        "--exclude-module", "matplotlib.tests",
        "--exclude-module", "vispy.testing",
        "--exclude-module", "OpenGL.Tk"
    )
    $pyInstallerArgs += $ortoolsBinaryArgs

    Write-Host "PyInstaller build basliyor: $Arch ($($python -join ' '))"
    Invoke-PythonCommand -PythonCommand $python -Arguments $pyInstallerArgs

    if (-not (Test-Path $exePath)) {
        throw "PyInstaller ciktisi bulunamadi: $exePath"
    }

    Write-Host "PyInstaller build hazir: $appDistDir"
}

function Build-InstallerTarget {
    param(
        [ValidateSet("x86", "x64")] [string] $Arch,
        [string] $InnoCompiler
    )

    $appDistDir = Join-Path $RootDir "dist\windows\$Arch\FlatCAMPlus"
    $exePath = Join-Path $appDistDir "FlatCAMPlus.exe"
    if (-not (Test-Path $exePath)) {
        throw "$Arch installer icin PyInstaller ciktisi bulunamadi: $exePath"
    }

    $installerArch = Get-InstallerArchLabel $Arch
    $iconPath = Join-Path $RootDir "build\icons\FlatCAMPlus.ico"
    if (-not (Test-Path $iconPath)) {
        $python = Resolve-PythonForArch $Arch
        $iconPath = New-AppIcon $python
    }

    Write-Host "Inno Setup installer basliyor: $Arch"
    & $InnoCompiler "/DAppVersion=""$Version""" "/DAppArch=""$Arch""" "/DAppInstallerArch=""$installerArch""" "/DAppIconFile=""$iconPath""" $InstallerScript

    if ($LASTEXITCODE -ne 0) {
        throw "$Arch Inno Setup installer derlemesi basarisiz oldu."
    }

    Write-Host "Installer hazir: $(Join-Path $RootDir "dist\installer\FlatCAMPlus-Setup-$Version-$installerArch.exe")"
}

$targets = if ($Target -eq "both") { @("x86", "x64") } else { @(ConvertTo-CanonicalArch $Target) }
$InnoCompiler = $null

if (-not $SkipInstaller) {
    $InnoCompiler = Find-InnoCompiler
}

if (-not $SkipPyInstaller) {
    Compile-Translations
    foreach ($arch in $targets) {
        Build-PyInstallerTarget $arch
    }
}

if (-not $SkipInstaller) {
    New-Item -ItemType Directory -Force -Path (Join-Path $RootDir "dist\installer") | Out-Null
    foreach ($arch in $targets) {
        Build-InstallerTarget $arch $InnoCompiler
    }
}

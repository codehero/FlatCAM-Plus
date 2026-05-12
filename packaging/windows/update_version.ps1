# ##########################################################
# FlatCAM Plus - Versiyon Guncelleme Yardimcisi
# Cagrilir: update_version.ps1 -Version "1.2.3" -RootDir "..."
# ##########################################################

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Version,

    [Parameter(Mandatory = $true)]
    [string] $RootDir
)

$ErrorActionPreference = "Stop"

# ---- appVersion.py ----
$releaseDate = Get-Date -Format "yyyy/MM/dd"
$versionFile = Join-Path $RootDir "appVersion.py"

if (-not (Test-Path $versionFile)) {
    throw "Dosya bulunamadi: $versionFile"
}

$content = Get-Content $versionFile -Raw -Encoding UTF8
$content = $content -replace 'APP_VERSION\s*=\s*"[^"]*"', "APP_VERSION = `"$Version`""
$content = $content -replace 'APP_VERSION_DATE\s*=\s*"[^"]*"', "APP_VERSION_DATE = `"$releaseDate`""
[System.IO.File]::WriteAllText($versionFile, $content, [System.Text.Encoding]::UTF8)
Write-Host "[OK] appVersion.py guncellendi: $Version ($releaseDate)"

# ---- FlatCAMPlus.iss ----
$issFile = Join-Path $RootDir "packaging\windows\FlatCAMPlus.iss"

if (-not (Test-Path $issFile)) {
    Write-Warning "FlatCAMPlus.iss bulunamadi, atlanıyor: $issFile"
} else {
    $issContent = Get-Content $issFile -Raw -Encoding UTF8
    $issContent = $issContent -replace '#define AppVersion\s+"[^"]*"', "#define AppVersion `"$Version`""
    [System.IO.File]::WriteAllText($issFile, $issContent, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] FlatCAMPlus.iss guncellendi: $Version"
}

Write-Host ""
Write-Host "Versiyon guncelleme tamamlandi: $Version"

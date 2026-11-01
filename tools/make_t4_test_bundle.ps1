<#
.SYNOPSIS
  Make one dated launcher/T4 test zip with a verified portable runtime.
.DESCRIPTION
  Downloads pinned Windows x64 runtime archives once and verifies SHA-256 sums.
  Both source catalogs and the exact runtime catalog must pass their scanners.
.PARAMETER T4Source
  Read-only T4 source tree. The source catalog is never built or launched.
.PARAMETER RuntimeRoot
  Verified portable runtime directory; defaults to dist\portable-runtime.
.PARAMETER CacheDirectory
  Download cache; defaults to dist\portable-cache.
.PARAMETER CheckOnly
  Run available source/runtime scans without fetching or creating a zip.
#>
param(
    [string]$T4Source = '',
    [string]$RuntimeRoot = '',
    [string]$CacheDirectory = '',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$Root = Split-Path -Parent $PSScriptRoot
if (-not $RuntimeRoot) { $RuntimeRoot = Join-Path $Root 'dist\portable-runtime' }
if (-not $CacheDirectory) { $CacheDirectory = Join-Path $Root 'dist\portable-cache' }
$RuntimePython = Join-Path $RuntimeRoot 'python.exe'
$Python = $null
$Prefix = @()

if (-not $CheckOnly) {
    $global:LASTEXITCODE = 0
    & (Join-Path $PSScriptRoot 'fetch_portable_runtime.ps1') -Destination $RuntimeRoot -CacheDirectory $CacheDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Portable Laufzeit konnte nicht vorbereitet werden.' }
    if (-not (Test-Path -LiteralPath $RuntimePython -PathType Leaf)) {
        throw 'Der gepruefte portable Laufzeitordner ist unvollstaendig.'
    }
    $Python = $RuntimePython
    $Probe = "import sys, struct; from PySide6 import QtCore, QtGui, QtQml, QtQuick; assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8; print('Portable runtime: Python 3.12, Qt ' + QtCore.qVersion())"
    & $Python -I -B -c $Probe
    if ($LASTEXITCODE -ne 0) { throw 'Portable Laufzeit oder Qt konnte nicht geladen werden.' }
} else {
    if (Test-Path -LiteralPath $RuntimePython -PathType Leaf) {
        $global:LASTEXITCODE = 0
        & (Join-Path $PSScriptRoot 'fetch_portable_runtime.ps1') -Destination $RuntimeRoot -CacheDirectory $CacheDirectory -CheckOnly
        if ($LASTEXITCODE -ne 0) { throw 'Portable Laufzeit konnte nicht geprueft werden.' }
    }
    $LocalPython = Join-Path $Root '.venv\Scripts\python.exe'
    $Candidates = @($RuntimePython, $LocalPython, 'py', 'python', 'python3')
    foreach ($Name in $Candidates) {
        $Command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $Command) { continue }
        $CandidatePrefix = if ($Name -eq 'py') { @('-3.12') } else { @() }
        try {
            & $Command.Source @CandidatePrefix -I -B -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) {
                $Python = $Command.Source
                $Prefix = @($CandidatePrefix)
                break
            }
        } catch { }
    }
    if (-not $Python) { throw 'Keine Laufzeit fuer die Pruefung vorhanden. Das Skript zuerst ohne -CheckOnly ausfuehren.' }
}

$Arguments = @($Prefix) + @('-I', '-B', (Join-Path $PSScriptRoot 't4_test_bundle.py'), '--root', $Root)
if (Test-Path -LiteralPath $RuntimePython -PathType Leaf) {
    $Arguments += @('--runtime', $RuntimeRoot, '--runtime-cache', $CacheDirectory)
}
if ($T4Source) { $Arguments += @('--t4-source', $T4Source) }
if ($CheckOnly) { $Arguments += '--check-only' }
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw 'Test-Bundle verweigert. Die oben genannten Quelldateien pruefen.' }

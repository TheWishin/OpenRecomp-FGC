<#
.SYNOPSIS
  Make one dated source-only launcher/T4 test zip in dist, without Git or a build.
.DESCRIPTION
  Both source catalogs must pass their existing scanners. No portable Python,
  executables, game files or images are included. run.cmd stays unchanged.
.PARAMETER T4Source
  Read-only T4 Sunday source tree. By default, use the maintainer's sibling workspace.
.PARAMETER CheckOnly
  Run both scans without creating a directory or zip.
#>
param([string]$T4Source = '', [switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$Root = Split-Path -Parent $PSScriptRoot
$Python = $null
$Prefix = @()
$LocalPython = Join-Path $Root '.venv\Scripts\python.exe'
$Candidates = @($LocalPython, 'py', 'python', 'python3')
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
if (-not $Python) { throw 'Python 3.12 fehlt. Python 3.12 installieren und erneut versuchen.' }
$Arguments = @($Prefix) + @('-I', '-B', (Join-Path $PSScriptRoot 't4_test_bundle.py'), '--root', $Root)
if ($T4Source) { $Arguments += @('--t4-source', $T4Source) }
if ($CheckOnly) { $Arguments += '--check-only' }
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw 'Test-Bundle verweigert. Die oben genannten Quelldateien pruefen.' }

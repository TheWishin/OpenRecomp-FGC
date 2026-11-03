<#
.SYNOPSIS
  The test zip for both games (Tekken 4 source + launcher; players add their own T5DR-Online-1.2.0 folder).
.DESCRIPTION
  Same as make_t4_test_bundle.ps1, which kept its name for older notes. Every parameter is passed on.
#>
param(
    [string]$T4Source = '',
    [string]$RuntimeRoot = '',
    [string]$CacheDirectory = '',
    [string]$OutputDirectory = '',
    [string[]]$Note = @(),
    [string[]]$Forbid = @(),
    [string]$ReleaseTag = '',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'make_t4_test_bundle.ps1') @PSBoundParameters

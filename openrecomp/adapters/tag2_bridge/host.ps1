# Hosts the installed TAG2 PC launcher Core for OpenRecomp-FGC (see Tag2Bridge.cs and docs/TAG2.md).
# The Core file is checked against the SHA-256 the launcher expects before it is loaded; nothing is downloaded,
# installed or changed here.
param(
    [Parameter(Mandatory = $true)][string]$Core,
    [Parameter(Mandatory = $true)][string]$CoreSha256,
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Agent,
    [Parameter(Mandatory = $true)][string]$Bridge
)
$ErrorActionPreference = 'Stop'
try {
    $actual = (Get-FileHash -LiteralPath $Core -Algorithm SHA256).Hash
    if ($actual -ne $CoreSha256.ToUpperInvariant()) { [Console]::Error.WriteLine('core-hash'); exit 3 }
    Add-Type -Path $Core
    $references = @('System', 'System.Core', 'System.Net.Http', 'System.Web.Extensions', $Core)
    Add-Type -TypeDefinition ([IO.File]::ReadAllText($Bridge)) -ReferencedAssemblies $references
} catch {
    [Console]::Error.WriteLine('core-load: ' + $_.Exception.Message)
    exit 4
}
exit [OpenRecomp.Tag2.Bridge]::Run($Root, $Agent)

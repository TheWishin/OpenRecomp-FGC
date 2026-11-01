<# Run the actual PowerShell fetch entry point against harmless local ZIPs. #>
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$Root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Fetcher = Join-Path $Root 'tools\fetch_portable_runtime.ps1'
$Temporary = Join-Path $Root ('.portable-scan-test-' + [Guid]::NewGuid().ToString('N'))
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression

function Hash-Bytes([byte[]]$Bytes) {
    $Hash = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($Hash.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $Hash.Dispose() }
}

function New-Fixture([string]$Name) {
    $Directory = Join-Path $Temporary $Name
    $Cache = Join-Path $Directory 'cache'
    New-Item -ItemType Directory -Force -Path $Cache | Out-Null
    $ArchivePath = Join-Path $Cache 'fixture.zip'
    $Archive = [IO.Compression.ZipFile]::Open($ArchivePath, [IO.Compression.ZipArchiveMode]::Create)
    $Payloads = [ordered]@{
        'python.exe' = 'Synthetic runtime fixture; no executable code.'
        'LICENSE.txt' = 'Synthetic dependency license fixture retained alongside the runtime.'
    }
    $Files = [ordered]@{}
    try {
        foreach ($Name in $Payloads.Keys) {
            $Bytes = [Text.Encoding]::UTF8.GetBytes($Payloads[$Name])
            $Entry = $Archive.CreateEntry($Name)
            $Stream = $Entry.Open()
            try { $Stream.Write($Bytes, 0, $Bytes.Length) } finally { $Stream.Dispose() }
            $Files[$Name] = [ordered]@{ archive='fixture'; member=$Name; size=$Bytes.Length; sha256=(Hash-Bytes $Bytes) }
        }
    } finally { $Archive.Dispose() }
    $Configuration = "python312.zip`n.`nLib/site-packages`n..`n"
    $Bytes = [Text.Encoding]::UTF8.GetBytes($Configuration)
    $Files['python312._pth'] = [ordered]@{ content_utf8=$Configuration; size=$Bytes.Length; sha256=(Hash-Bytes $Bytes) }
    $Lock = [ordered]@{
        schema=1
        archives=@([ordered]@{ id='fixture'; filename='fixture.zip'; target_prefix=''; url='https://example.invalid/never-downloaded.zip';
            size=(Get-Item -LiteralPath $ArchivePath).Length;
            sha256=(Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant() })
        files=$Files
    }
    $LockPath = Join-Path $Directory 'lock.json'
    $Lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $LockPath -Encoding UTF8
    return @{ directory=$Directory; cache=$Cache; archive=$ArchivePath; lock=$Lock; lock_path=$LockPath;
              runtime=(Join-Path $Directory 'runtime') }
}

function Save-Lock($Fixture) {
    $Fixture.lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Fixture.lock_path -Encoding UTF8
}

function Invoke-Fixture($Fixture, [bool]$Success) {
    # Native PowerShell errors are captured as output; the child exit code is
    # the assertion. This does not alter execution policy or security settings.
    $Previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $Output = & powershell.exe -NoProfile -File $Fetcher -Destination $Fixture.runtime -CacheDirectory $Fixture.cache -LockPath $Fixture.lock_path 2>&1
        $Code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $Previous }
    if (($Code -eq 0) -ne $Success) { throw ('Unexpected fetch exit code {0}: {1}' -f $Code, ($Output -join "`n")) }
}

try {
    New-Item -ItemType Directory -Path $Temporary | Out-Null
    $Good = New-Fixture 'good'
    Invoke-Fixture $Good $true
    if ([IO.File]::ReadAllText((Join-Path $Good.runtime 'LICENSE.txt')) -notmatch 'license fixture') {
        throw 'Runtime license did not survive extraction.'
    }
    Invoke-Fixture $Good $true
    Write-Output 'PASS: real fetch entry point extracts pinned files, retains license and verifies an existing runtime.'

    $Prefix = New-Fixture 'prefix'
    $Prefix.lock.archives[0].target_prefix = 'Lib/site-packages'
    Save-Lock $Prefix
    Invoke-Fixture $Prefix $true
    if (-not (Test-Path -LiteralPath (Join-Path $Prefix.runtime 'Lib/site-packages/LICENSE.txt'))) {
        throw 'Archive target prefix was not separated from its member path.'
    }
    Write-Output 'PASS: wheel-style target prefixes insert their directory separator.'

    [IO.File]::WriteAllText((Join-Path $Good.runtime 'python.exe'), 'Changed runtime bytes')
    Invoke-Fixture $Good $false
    Write-Output 'PASS: changed installed runtime is refused.'

    $Extra = New-Fixture 'extra'
    Invoke-Fixture $Extra $true
    [IO.File]::WriteAllText((Join-Path $Extra.runtime 'unexpected.dll'), 'Uncataloged synthetic fixture')
    Invoke-Fixture $Extra $false
    Write-Output 'PASS: uncataloged runtime binary is refused.'

    $Archive = New-Fixture 'archive'
    [IO.File]::AppendAllText($Archive.archive, 'Changed archive bytes')
    Invoke-Fixture $Archive $false
    if (Test-Path -LiteralPath $Archive.runtime) { throw 'Bad archive produced a runtime.' }
    Write-Output 'PASS: archive SHA-256/size failure produces no runtime.'

    $Member = New-Fixture 'member'
    $Member.lock.files['python.exe'].sha256 = '0' * 64
    Save-Lock $Member
    Invoke-Fixture $Member $false
    if (Test-Path -LiteralPath $Member.runtime) { throw 'Bad member produced a runtime.' }
    Write-Output 'PASS: extracted member SHA-256 failure produces no runtime.'

    foreach ($Unsafe in @('../escape.txt', 'directory/../../escape.txt', 'directory\alias.txt', 'NUL.txt', 'trailing.')) {
        $Fixture = New-Fixture ('unsafe-' + [Guid]::NewGuid().ToString('N'))
        $Fixture.lock.files[$Unsafe] = [ordered]@{ content_utf8='fixture'; size=7; sha256=(Hash-Bytes ([Text.Encoding]::UTF8.GetBytes('fixture'))) }
        Save-Lock $Fixture
        Invoke-Fixture $Fixture $false
        if (Test-Path -LiteralPath $Fixture.runtime) { throw 'Unsafe path produced a runtime.' }
    }
    Write-Output 'PASS: traversal, separator aliases, reserved devices and trailing dots are refused.'
    Write-Output 'Portable scan entry-point checks passed (11 fixture scenarios).'
} finally {
    $Resolved = [IO.Path]::GetFullPath($Temporary)
    if (-not $Resolved.StartsWith($Root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to remove a test directory outside the repository.'
    }
    if (Test-Path -LiteralPath $Resolved) { Remove-Item -LiteralPath $Resolved -Recurse -Force }
}

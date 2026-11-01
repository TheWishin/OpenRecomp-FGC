# Exercise the real fetch entry point with local, pinned ZIP fixtures. No window.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$Root = Split-Path -Parent $PSScriptRoot
$Fetcher = Join-Path $Root 'tools\fetch_portable_runtime.ps1'
$Work = Join-Path $Root ('dist\portable-fetch-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Work | Out-Null

function Hash-Bytes([byte[]]$Bytes) {
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($Hasher.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $Hasher.Dispose() }
}

function New-Fixture([string]$Name) {
    $Directory = Join-Path $Work $Name
    $Cache = Join-Path $Directory 'cache'
    New-Item -ItemType Directory -Force -Path $Cache | Out-Null
    $Archive = Join-Path $Cache 'fixture.zip'
    $Zip = [IO.Compression.ZipFile]::Open($Archive, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($NameAndContent in @(@('python.exe', 'MZfixture only'), @('LICENSE.txt', 'Fixture licence'), @('python312._pth', 'old configuration'))) {
            $Entry = $Zip.CreateEntry($NameAndContent[0])
            $Stream = $Entry.Open()
            try {
                $Bytes = [Text.Encoding]::UTF8.GetBytes($NameAndContent[1])
                $Stream.Write($Bytes, 0, $Bytes.Length)
            } finally { $Stream.Dispose() }
        }
    } finally { $Zip.Dispose() }
    $Configuration = "python312.zip`n.`n..`nLib/site-packages`nimport site`n"
    $ConfigBytes = [Text.Encoding]::UTF8.GetBytes($Configuration)
    $Lock = [ordered]@{
        schema = 1
        archives = @(@{id='fixture'; filename='fixture.zip'; url='https://example.invalid/fixture.zip';
            sha256=(Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant();
            size=(Get-Item -LiteralPath $Archive).Length; target_prefix=''})
        files = @{'python312._pth'=@{content_utf8=$Configuration; size=$ConfigBytes.Length; sha256=(Hash-Bytes $ConfigBytes)}}
    }
    $LockPath = Join-Path $Directory 'lock.json'
    $Lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $LockPath -Encoding UTF8
    return [pscustomobject]@{Directory=$Directory; Cache=$Cache; Destination=(Join-Path $Directory 'runtime'); LockPath=$LockPath; Lock=$Lock; Configuration=$Configuration}
}

function Invoke-Fetch($Fixture, [switch]$CheckOnly) {
    $Arguments = @('-NoProfile', '-File', $Fetcher, '-Destination', $Fixture.Destination,
        '-CacheDirectory', $Fixture.Cache, '-LockPath', $Fixture.LockPath)
    if ($CheckOnly) { $Arguments += '-CheckOnly' }
    $Previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $Messages = & (Join-Path $PSHOME 'powershell.exe') @Arguments 2>&1
        return [pscustomobject]@{Code=$LASTEXITCODE; Text=($Messages | Out-String)}
    } finally { $ErrorActionPreference = $Previous }
}

function Require([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

try {
    $Valid = New-Fixture 'valid'
    $Result = Invoke-Fetch $Valid
    Require ($Result.Code -eq 0) ('Valid pinned fixture failed: ' + $Result.Text)
    Require ([IO.File]::ReadAllText((Join-Path $Valid.Destination 'python312._pth')) -ceq $Valid.Configuration) 'Generated configuration was not installed.'
    Require (Test-Path -LiteralPath (Join-Path $Valid.Destination 'LICENSE.txt')) 'Licence was not retained.'
    $Result = Invoke-Fetch $Valid -CheckOnly
    Require ($Result.Code -eq 0) ('Read-only verification failed: ' + $Result.Text)
    Set-Content -LiteralPath (Join-Path $Valid.Destination 'unexpected.dll') -Value 'Unexpected'
    Require ((Invoke-Fetch $Valid -CheckOnly).Code -ne 0) 'Unexpected runtime file was accepted.'

    $WrongArchive = New-Fixture 'wrong-archive'
    $WrongArchive.Lock.archives[0].sha256 = ('0' * 64)
    $WrongArchive.Lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $WrongArchive.LockPath -Encoding UTF8
    Require ((Invoke-Fetch $WrongArchive).Code -ne 0) 'Archive with wrong SHA-256 was accepted.'
    Require (-not (Test-Path -LiteralPath $WrongArchive.Destination)) 'Failed archive left a runtime destination.'

    $WrongGenerated = New-Fixture 'wrong-generated'
    $WrongGenerated.Lock.files['python312._pth'].sha256 = ('0' * 64)
    $WrongGenerated.Lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $WrongGenerated.LockPath -Encoding UTF8
    Require ((Invoke-Fetch $WrongGenerated).Code -ne 0) 'Generated file with wrong SHA-256 was accepted.'
    Require (-not (Test-Path -LiteralPath $WrongGenerated.Destination)) 'Failed extraction left a runtime destination.'
    Require (@(Get-ChildItem -LiteralPath $WrongGenerated.Directory -Directory -Filter '.portable-stage-*').Count -eq 0) 'Failed extraction left a stage directory.'

    $Traversal = New-Fixture 'traversal'
    $Traversal.Lock.files['../escaped.txt'] = $Traversal.Lock.files['python312._pth']
    $Traversal.Lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Traversal.LockPath -Encoding UTF8
    Require ((Invoke-Fetch $Traversal).Code -ne 0) 'Catalog traversal was accepted.'
    Require (-not (Test-Path -LiteralPath (Join-Path $Traversal.Directory 'escaped.txt'))) 'Catalog traversal wrote outside its runtime.'

    $ReadOnly = New-Fixture 'read-only'
    Require ((Invoke-Fetch $ReadOnly -CheckOnly).Code -ne 0) 'Read-only check accepted a missing runtime.'
    Require (-not (Test-Path -LiteralPath $ReadOnly.Destination)) 'Read-only check wrote a runtime.'

    $Prefixed = New-Fixture 'prefixed'
    $Prefixed.Lock.archives[0].target_prefix = 'Lib/site-packages'
    $Prefixed.Lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Prefixed.LockPath -Encoding UTF8
    $Result = Invoke-Fetch $Prefixed
    Require ($Result.Code -eq 0) ('Wheel prefix fixture failed: ' + $Result.Text)
    Require (Test-Path -LiteralPath (Join-Path $Prefixed.Destination 'Lib/site-packages/LICENSE.txt')) 'Archive target prefix was not separated from the member path.'

    $Licensed = New-Fixture 'licensed'
    $Source = Join-Path $Licensed.Cache 'source.zip'
    $Zip = [IO.Compression.ZipFile]::Open($Source, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($Pair in @(@('source/LICENSES/LGPL-3.0.txt', 'GNU LESSER GENERAL PUBLIC LICENSE Version 3'),
                @('source/LICENSES/GPL-3.0.txt', 'GNU GENERAL PUBLIC LICENSE Version 3'), @('source/unused.py', 'Not a licence'))) {
            $Entry = $Zip.CreateEntry($Pair[0])
            $Stream = $Entry.Open()
            try {
                $Bytes = [Text.Encoding]::UTF8.GetBytes($Pair[1])
                $Stream.Write($Bytes, 0, $Bytes.Length)
            } finally { $Stream.Dispose() }
        }
    } finally { $Zip.Dispose() }
    $Licensed.Lock['downloads'] = @(@{filename='source.zip'; url='https://example.invalid/source.zip';
        sha256=(Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant();
        size=(Get-Item -LiteralPath $Source).Length; target='licenses/sources/source.zip'; licenses_prefix='licenses/PySide6'})
    $Licensed.Lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Licensed.LockPath -Encoding UTF8
    $Result = Invoke-Fetch $Licensed
    Require ($Result.Code -eq 0) ('Pinned license resource failed: ' + $Result.Text)
    Require (Test-Path -LiteralPath (Join-Path $Licensed.Destination 'licenses/sources/source.zip')) 'Pinned source archive was not retained.'
    Require (Test-Path -LiteralPath (Join-Path $Licensed.Destination 'licenses/PySide6/LICENSES/LGPL-3.0.txt')) 'LGPL text was not retained.'
    Require (Test-Path -LiteralPath (Join-Path $Licensed.Destination 'licenses/PySide6/LICENSES/GPL-3.0.txt')) 'GPL text was not retained.'
    Require (-not (Test-Path -LiteralPath (Join-Path $Licensed.Destination 'licenses/PySide6/unused.py'))) 'Unselected source code was extracted.'
    Require ((Invoke-Fetch $Licensed -CheckOnly).Code -eq 0) 'Read-only license resource validation failed.'

    $Linked = New-Fixture 'linked'
    $LinkedZipPath = Join-Path $Linked.Cache 'fixture.zip'
    $Zip = [IO.Compression.ZipFile]::Open($LinkedZipPath, [IO.Compression.ZipArchiveMode]::Update)
    try {
        $Entry = $Zip.CreateEntry('linked-file')
        $Entry.ExternalAttributes = -1577123840
    } finally { $Zip.Dispose() }
    $Linked.Lock.archives[0].sha256 = (Get-FileHash -LiteralPath $LinkedZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $Linked.Lock.archives[0].size = (Get-Item -LiteralPath $LinkedZipPath).Length
    $Linked.Lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Linked.LockPath -Encoding UTF8
    Require ((Invoke-Fetch $Linked).Code -ne 0) 'Linked archive member was accepted.'

    $Encrypted = New-Fixture 'encrypted'
    $EncryptedPath = Join-Path $Encrypted.Cache 'fixture.zip'
    $Bytes = [IO.File]::ReadAllBytes($EncryptedPath)
    for ($Index = 0; $Index -lt $Bytes.Length - 10; $Index++) {
        if ([BitConverter]::ToUInt32($Bytes, $Index) -eq 0x02014b50) { $Bytes[$Index + 8] = $Bytes[$Index + 8] -bor 1 }
        if ([BitConverter]::ToUInt32($Bytes, $Index) -eq 0x04034b50) { $Bytes[$Index + 6] = $Bytes[$Index + 6] -bor 1 }
    }
    [IO.File]::WriteAllBytes($EncryptedPath, $Bytes)
    $Encrypted.Lock.archives[0].sha256 = (Get-FileHash -LiteralPath $EncryptedPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $Encrypted.Lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Encrypted.LockPath -Encoding UTF8
    Require ((Invoke-Fetch $Encrypted).Code -ne 0) 'Encrypted ZIP member flag was accepted.'
    Write-Output 'Portable fetch entry-point checks passed (cached ZIP fixtures; no network or interpreter execution).'
} finally {
    $ResolvedWork = [IO.Path]::GetFullPath($Work)
    $Allowed = [IO.Path]::GetFullPath((Join-Path $Root 'dist')) + [IO.Path]::DirectorySeparatorChar
    if (-not $ResolvedWork.StartsWith($Allowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe fixture cleanup path.' }
    Remove-Item -LiteralPath $ResolvedWork -Recurse -Force
}

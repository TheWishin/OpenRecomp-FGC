<#
.SYNOPSIS
  Fetch and verify the pinned Windows x64 test-bundle runtime, without Python.
.DESCRIPTION
  Downloads only the archives named in portable_runtime.lock.json. Both archive
  and extracted-file SHA-256 sums must match. Existing runtimes are verified.
#>
param(
    [string]$Destination = '',
    [string]$CacheDirectory = '',
    [string]$LockPath = '',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$MaxArchiveSize = 128 * 1024 * 1024
$MaxMemberSize = 128 * 1024 * 1024
$MaxRuntimeSize = 512 * 1024 * 1024
$Root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $Destination) { $Destination = Join-Path $Root 'dist\portable-runtime' }
if (-not $CacheDirectory) { $CacheDirectory = Join-Path $Root 'dist\portable-cache' }
if (-not $LockPath) { $LockPath = Join-Path $PSScriptRoot 'portable_runtime.lock.json' }

function Assert-LocalPath([string]$Path) {
    $Full = [IO.Path]::GetFullPath($Path)
    if (-not $Full.StartsWith($Root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Portable runtime paths must stay inside this repository.'
    }
    $Current = $Full
    while ($Current -and $Current.Length -ge $Root.Length) {
        if (Test-Path -LiteralPath $Current) {
            if ((Get-Item -Force -LiteralPath $Current).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Links and junctions are not allowed in portable runtime paths.'
            }
        }
        $Current = [IO.Path]::GetDirectoryName($Current)
    }
    return $Full
}

function Assert-RelativeName([string]$Name) {
    if (-not $Name -or $Name -match '[\\:<>"|?*\x00-\x1f]' -or $Name.StartsWith('/') -or
        @($Name.Split('/') | Where-Object {
            -not $_ -or $_ -eq '.' -or $_ -eq '..' -or $_ -match '[. ]$' -or
            $_ -match '^(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)'
        }).Count) {
        throw 'Unsafe portable runtime catalog path.'
    }
}

function Get-BytesHash([byte[]]$Bytes) {
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($Hasher.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $Hasher.Dispose() }
}

function Assert-File([string]$Path, $Record) {
    Assert-LocalPath $Path | Out-Null
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or
        ($Record.PSObject.Properties['size'] -and (Get-Item -LiteralPath $Path).Length -ne [long]$Record.size) -or
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -cne [string]$Record.sha256) {
        throw 'Portable runtime file is missing or its size/SHA-256 does not match.'
    }
}

function Assert-ZipFlags([string]$Path) {
    # Windows PowerShell's .NET ZIP reader does not consistently expose or
    # reject the encrypted-entry flag. Read it from the central directory.
    $Stream = [IO.File]::OpenRead($Path)
    $Reader = New-Object IO.BinaryReader($Stream)
    try {
        $TailLength = [int][Math]::Min(65557, $Stream.Length)
        $Stream.Position = $Stream.Length - $TailLength
        $Tail = $Reader.ReadBytes($TailLength)
        $End = -1
        for ($Index = $Tail.Length - 22; $Index -ge 0; $Index--) {
            if ([BitConverter]::ToUInt32($Tail, $Index) -eq 0x06054b50 -and
                $Index + 22 + [BitConverter]::ToUInt16($Tail, $Index + 20) -eq $Tail.Length) { $End = $Index; break }
        }
        if ($End -lt 0) { throw 'Pinned ZIP has no valid central directory.' }
        $Count = [BitConverter]::ToUInt16($Tail, $End + 10)
        $Offset = [BitConverter]::ToUInt32($Tail, $End + 16)
        if ($Count -eq 65535 -or $Offset -eq [uint32]::MaxValue -or
            [BitConverter]::ToUInt16($Tail, $End + 4) -ne 0 -or [BitConverter]::ToUInt16($Tail, $End + 6) -ne 0) {
            throw 'Split and ZIP64 runtime archives are not supported.'
        }
        $Stream.Position = $Offset
        for ($Index = 0; $Index -lt $Count; $Index++) {
            if ($Reader.ReadUInt32() -ne 0x02014b50) { throw 'Invalid ZIP central directory entry.' }
            $Header = $Reader.ReadBytes(42)
            if ($Header.Length -ne 42 -or ([BitConverter]::ToUInt16($Header, 4) -band 1)) { throw 'Encrypted or truncated runtime ZIP member.' }
            $Skip = [BitConverter]::ToUInt16($Header, 24) + [BitConverter]::ToUInt16($Header, 26) + [BitConverter]::ToUInt16($Header, 28)
            $Stream.Seek($Skip, [IO.SeekOrigin]::Current) | Out-Null
        }
    } finally { $Reader.Dispose(); $Stream.Dispose() }
}

function Assert-Runtime([string]$Directory, $Files) {
    $Expected = @{}
    foreach ($Property in $Files.PSObject.Properties) {
        $Name = $Property.Name
        Assert-RelativeName $Name
        if ($Expected.ContainsKey($Name)) { throw 'Case-colliding portable runtime catalog paths.' }
        $Expected[$Name] = $Name
        Assert-File (Join-Path $Directory $Name) $Property.Value
    }
    $Actual = @(Get-ChildItem -LiteralPath $Directory -Recurse -Force)
    foreach ($Item in $Actual) {
        if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Portable runtime contains a link or junction.' }
        if (-not $Item.PSIsContainer) {
            $Relative = $Item.FullName.Substring($Directory.Length + 1).Replace('\', '/')
            if (-not $Expected.ContainsKey($Relative) -or $Expected[$Relative] -cne $Relative) {
                throw 'Unexpected file or casing in portable runtime.'
            }
        }
    }
}

$Destination = Assert-LocalPath $Destination
$CacheDirectory = Assert-LocalPath $CacheDirectory
$LockPath = Assert-LocalPath $LockPath
$Lock = Get-Content -Raw -LiteralPath $LockPath | ConvertFrom-Json
if ($Lock.schema -ne 1 -or -not @($Lock.files.PSObject.Properties).Count) { throw 'Unsupported portable runtime catalog.' }
$ArchiveById = @{}
foreach ($Archive in $Lock.archives) {
    if ($Archive.id -notmatch '^[a-zA-Z0-9_-]+$' -or $ArchiveById.ContainsKey($Archive.id) -or
        $Archive.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        ($Archive.PSObject.Properties['size'] -and [long]$Archive.size -le 0)) {
        throw 'Invalid pinned archive record.'
    }
    $Uri = [Uri]$Archive.url
    if (-not $Uri.IsAbsoluteUri -or $Uri.Scheme -ne 'https') { throw 'Pinned downloads must use HTTPS.' }
    Assert-RelativeName $Archive.filename
    if ($Archive.filename.Contains('/')) { throw 'Pinned archive filename must be a single filename.' }
    if ($Archive.target_prefix) { Assert-RelativeName $Archive.target_prefix.TrimEnd('/') }
    $ArchiveById[$Archive.id] = $Archive
}
foreach ($Property in $Lock.files.PSObject.Properties) {
    Assert-RelativeName $Property.Name
    $Record = $Property.Value
    if ($Record.sha256 -cnotmatch '^[0-9a-f]{64}$' -or [long]$Record.size -lt 0 -or [long]$Record.size -gt $MaxMemberSize) { throw 'Invalid pinned file record.' }
    if (-not $Record.PSObject.Properties['content_utf8']) {
        if (-not $Record.PSObject.Properties['archive'] -or -not $ArchiveById.ContainsKey($Record.archive)) {
            throw 'Portable runtime file references an unknown archive.'
        }
        Assert-RelativeName $Record.member
    }
}
if (-not $CheckOnly) { New-Item -ItemType Directory -Force -Path $CacheDirectory | Out-Null }
$ArchivePaths = @{}
foreach ($Archive in $Lock.archives) {
    $Cached = Join-Path $CacheDirectory $Archive.filename
    Assert-LocalPath $Cached | Out-Null
    if (-not (Test-Path -LiteralPath $Cached)) {
        if ($CheckOnly) { throw 'Verified archive cache required for read-only runtime checking.' }
        $Partial = Join-Path $CacheDirectory ($Archive.id + '-' + [Guid]::NewGuid().ToString('N') + '.partial')
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Archive.url -OutFile $Partial
            Assert-File $Partial $Archive
            Move-Item -LiteralPath $Partial -Destination $Cached
        } finally {
            if (Test-Path -LiteralPath $Partial) { Remove-Item -LiteralPath $Partial }
        }
    }
    Assert-File $Cached $Archive
    if ((Get-Item -LiteralPath $Cached).Length -gt $MaxArchiveSize) { throw 'Oversized pinned runtime archive.' }
    $ArchivePaths[$Archive.id] = $Cached
}
$Downloads = @()
if ($Lock.PSObject.Properties['downloads']) { $Downloads = @($Lock.downloads) }
$DownloadPaths = @{}
foreach ($Download in $Downloads) {
    Assert-RelativeName $Download.filename
    Assert-RelativeName $Download.target
    if ($Download.filename.Contains('/') -or $Download.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        $DownloadPaths.ContainsKey($Download.filename)) { throw 'Invalid pinned resource record.' }
    $Uri = [Uri]$Download.url
    if (-not $Uri.IsAbsoluteUri -or $Uri.Scheme -ne 'https') { throw 'Pinned downloads must use HTTPS.' }
    $Cached = Assert-LocalPath (Join-Path $CacheDirectory $Download.filename)
    if (-not (Test-Path -LiteralPath $Cached)) {
        if ($CheckOnly) { throw 'Verified resource cache required for read-only runtime checking.' }
        $Partial = Join-Path $CacheDirectory ([Guid]::NewGuid().ToString('N') + '.partial')
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Download.url -OutFile $Partial
            Assert-File $Partial $Download
            Move-Item -LiteralPath $Partial -Destination $Cached
        } finally {
            if (Test-Path -LiteralPath $Partial) { Remove-Item -LiteralPath $Partial }
        }
    }
    Assert-File $Cached $Download
    if ((Get-Item -LiteralPath $Cached).Length -gt $MaxArchiveSize) { throw 'Oversized pinned runtime resource.' }
    $DownloadPaths[$Download.filename] = $Cached
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$Expected = @{}
$RuntimeSize = [long]0
foreach ($Archive in $Lock.archives) {
    Assert-ZipFlags $ArchivePaths[$Archive.id]
    $Zip = [IO.Compression.ZipFile]::OpenRead($ArchivePaths[$Archive.id])
    try {
        foreach ($Member in $Zip.Entries) {
            if ($Member.FullName.EndsWith('/')) {
                Assert-RelativeName $Member.FullName.TrimEnd('/')
                continue
            }
            Assert-RelativeName $Member.FullName
            if ((($Member.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'Linked archive members are not permitted.' }
            $RuntimeSize += $Member.Length
            if ($Member.Length -gt $MaxMemberSize -or $RuntimeSize -gt $MaxRuntimeSize) { throw 'Oversized pinned runtime member or runtime.' }
            $Prefix = [string]$Archive.target_prefix
            if ($Prefix) { $Prefix = $Prefix.TrimEnd('/') + '/' }
            $Name = $Prefix + $Member.FullName
            Assert-RelativeName $Name
            if ($Expected.ContainsKey($Name)) { throw 'Duplicate or case-colliding archive member.' }
            $Stream = $Member.Open()
            $Hasher = [Security.Cryptography.SHA256]::Create()
            try { $Hash = ([BitConverter]::ToString($Hasher.ComputeHash($Stream))).Replace('-', '').ToLowerInvariant() }
            finally { $Hasher.Dispose(); $Stream.Dispose() }
            $Expected[$Name] = [pscustomobject]@{archive=$Archive.id; member=$Member.FullName; size=$Member.Length; sha256=$Hash}
        }
    } finally { $Zip.Dispose() }
}
foreach ($Property in $Lock.files.PSObject.Properties) {
    if ($Expected.ContainsKey($Property.Name) -and -not @($Expected.Keys | Where-Object { $_ -ceq $Property.Name }).Count) {
        throw 'Case-colliding generated runtime file.'
    }
    $Expected[$Property.Name] = $Property.Value
}
foreach ($Download in $Downloads) {
    if ($Expected.ContainsKey($Download.target)) { throw 'Duplicate pinned runtime resource target.' }
    $Length = (Get-Item -LiteralPath $DownloadPaths[$Download.filename]).Length
    $RuntimeSize += $Length
    if ($RuntimeSize -gt $MaxRuntimeSize) { throw 'Oversized pinned runtime.' }
    $Expected[$Download.target] = [pscustomobject]@{download=$Download.filename; size=$Length; sha256=$Download.sha256}
    if ($Download.PSObject.Properties['licenses_prefix']) {
        Assert-RelativeName $Download.licenses_prefix
        Assert-ZipFlags $DownloadPaths[$Download.filename]
        $Zip = [IO.Compression.ZipFile]::OpenRead($DownloadPaths[$Download.filename])
        try {
            $Members = @($Zip.Entries | Where-Object { -not $_.FullName.EndsWith('/') })
            if (-not $Members.Count) { throw 'Pinned licensing source archive is empty.' }
            $First = $Members[0].FullName.Split('/')[0]
            $StripTop = @($Members | Where-Object { -not $_.FullName.Contains('/') -or $_.FullName.Split('/')[0] -cne $First }).Count -eq 0
            $HasLgpl3 = $false
            $HasGpl3 = $false
            foreach ($Member in $Members) {
                Assert-RelativeName $Member.FullName
                $Relative = $Member.FullName
                if ($StripTop) { $Relative = $Relative.Substring($First.Length + 1) }
                $Parts = $Relative.Split('/')
                if ($Parts[0] -cne 'LICENSES' -and -not ($Parts.Count -eq 1 -and $Parts[0] -match '^(?i:LICENSE|COPYING)')) { continue }
                if ((($Member.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'Linked licensing source member.' }
                $RuntimeSize += $Member.Length
                if ($Member.Length -gt $MaxMemberSize -or $RuntimeSize -gt $MaxRuntimeSize) { throw 'Oversized licensing source member or runtime.' }
                $Name = $Download.licenses_prefix.TrimEnd('/') + '/' + $Relative
                Assert-RelativeName $Name
                if ($Expected.ContainsKey($Name)) { throw 'Duplicate licensing source member target.' }
                $InputStream = $Member.Open()
                $Memory = New-Object IO.MemoryStream
                try { $InputStream.CopyTo($Memory); $Bytes = $Memory.ToArray() }
                finally { $Memory.Dispose(); $InputStream.Dispose() }
                $Text = [Text.Encoding]::UTF8.GetString($Bytes).ToUpperInvariant()
                if ($Text.Contains('GNU LESSER GENERAL PUBLIC LICENSE') -and $Text.Contains('VERSION 3')) { $HasLgpl3 = $true }
                if ($Text.Contains('GNU GENERAL PUBLIC LICENSE') -and $Text.Contains('VERSION 3')) { $HasGpl3 = $true }
                $Expected[$Name] = [pscustomobject]@{archive=('download:' + $Download.filename); member=$Member.FullName; size=$Member.Length; sha256=(Get-BytesHash $Bytes)}
            }
            if (-not $HasLgpl3 -or -not $HasGpl3) {
                throw 'Pinned licensing source is missing the LGPL/GPL version 3 texts.'
            }
        } finally { $Zip.Dispose() }
    }
}
$Files = [pscustomobject]$Expected
$TotalExpected = ($Files.PSObject.Properties | ForEach-Object { [long]$_.Value.size } | Measure-Object -Sum).Sum
if ($TotalExpected -gt $MaxRuntimeSize) { throw 'Oversized pinned runtime.' }
if (Test-Path -LiteralPath $Destination) {
    Assert-Runtime $Destination $Files
    $Total = ($Files.PSObject.Properties | ForEach-Object { [long]$_.Value.size } | Measure-Object -Sum).Sum
    Write-Output ('Portable runtime verified: {0} files; {1:N0} bytes; no download needed.' -f @($Files.PSObject.Properties).Count, $Total)
    exit 0
}
if ($CheckOnly) { throw 'Portable runtime is not present.' }
$Parent = Split-Path -Parent $Destination
New-Item -ItemType Directory -Force -Path $Parent | Out-Null
$Stage = Assert-LocalPath (Join-Path $Parent ('.portable-stage-' + [Guid]::NewGuid().ToString('N')))
New-Item -ItemType Directory -Path $Stage | Out-Null
$Opened = @{}
try {
    foreach ($Archive in $Lock.archives) {
        $Opened[$Archive.id] = [IO.Compression.ZipFile]::OpenRead($ArchivePaths[$Archive.id])
    }
    foreach ($Download in $Downloads) {
        if ($Download.PSObject.Properties['licenses_prefix']) {
            $Opened['download:' + $Download.filename] = [IO.Compression.ZipFile]::OpenRead($DownloadPaths[$Download.filename])
        }
    }
    foreach ($Property in $Files.PSObject.Properties) {
        $Record = $Property.Value
        $Target = Assert-LocalPath (Join-Path $Stage $Property.Name)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
        if ($Record.PSObject.Properties['content_utf8']) {
            $Bytes = [Text.Encoding]::UTF8.GetBytes([string]$Record.content_utf8)
            if ($Bytes.Length -ne [long]$Record.size -or (Get-BytesHash $Bytes) -cne $Record.sha256) {
                throw 'Generated portable configuration does not match its catalog hash.'
            }
            [IO.File]::WriteAllBytes($Target, $Bytes)
        } elseif ($Record.PSObject.Properties['download']) {
            Copy-Item -LiteralPath $DownloadPaths[$Record.download] -Destination $Target
        } else {
            $Matches = @($Opened[$Record.archive].Entries | Where-Object { $_.FullName -ceq $Record.member })
            if ($Matches.Count -ne 1 -or $Matches[0].Length -ne [long]$Record.size) { throw 'Pinned archive member is missing, duplicated or oversized.' }
            $InputStream = $Matches[0].Open()
            try {
                $OutputStream = [IO.File]::Create($Target)
                try { $InputStream.CopyTo($OutputStream) } finally { $OutputStream.Dispose() }
            } finally { $InputStream.Dispose() }
        }
        Assert-File $Target $Record
    }
    Assert-Runtime $Stage $Files
    foreach ($OpenedArchive in $Opened.Values) { $OpenedArchive.Dispose() }
    $Opened.Clear()
    Move-Item -LiteralPath $Stage -Destination $Destination
    $Total = ($Files.PSObject.Properties | ForEach-Object { [long]$_.Value.size } | Measure-Object -Sum).Sum
    Write-Output ('Portable runtime ready: {0} files; {1:N0} bytes.' -f @($Files.PSObject.Properties).Count, $Total)
} finally {
    foreach ($OpenedArchive in $Opened.Values) { $OpenedArchive.Dispose() }
    if (Test-Path -LiteralPath $Stage) {
        # Stage was resolved and checked inside the repository before creation.
        Assert-LocalPath $Stage | Out-Null
        Remove-Item -LiteralPath $Stage -Recurse -Force
    }
}

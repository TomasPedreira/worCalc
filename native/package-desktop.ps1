# Build artifact packaging only; the application opens directly through its EXE.
param([ValidateSet('calculator','sketcher','kill-tracker')][string]$App = 'calculator')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$applications = Get-Content -LiteralPath (Join-Path $repoRoot 'native/apps.json') -Raw | ConvertFrom-Json
$application = $applications.$App
$version = (Get-Content -LiteralPath (Join-Path $repoRoot 'package.json') -Raw | ConvertFrom-Json).version
function Get-AssetSha256([string]$path) {
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($path)
    try { return [System.BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
$binary = Join-Path $repoRoot 'target/release/worcalc-app.exe'
if (-not (Test-Path -LiteralPath $binary)) { throw 'Build the release application first: npm.cmd run desktop:build' }
$binaryInfo = (Get-Item -LiteralPath $binary).VersionInfo
if ($binaryInfo.ProductName -ne $application.name -or $binaryInfo.ProductVersion -ne $version) {
    throw "The release executable is not $($application.name) $version. Build the selected app before packaging."
}
$inputs = @()
if ($application.maps) {
$manifest = Get-Content -LiteralPath (Join-Path $repoRoot 'native/assets/manifest.json') -Raw | ConvertFrom-Json
if ($manifest.version -ne 1) { throw 'Unsupported offline pack manifest' }
foreach ($entry in $manifest.files.PSObject.Properties) {
    if ($entry.Name -ne 'catalog.json' -and $entry.Name -notmatch '^(maps/map-\d+(-thumb)?\.webp|terrain/[A-Za-z0-9]+\.wrtz)$') {
        throw "Invalid resource path: $($entry.Name)"
    }
    $inputFile = Join-Path $repoRoot ('src-tauri/resources/' + $entry.Name)
    if (-not (Test-Path -LiteralPath $inputFile) -or (Get-Item -LiteralPath $inputFile).Length -ne $entry.Value.size -or
        (Get-AssetSha256 $inputFile) -ne $entry.Value.sha256) {
        throw "Missing or corrupt staged resource: $($entry.Name). Run npm.cmd run assets."
    }
    $inputs += [pscustomobject]@{Path=$inputFile; RelativePath=$entry.Name}
}
}
$artifactDirectory = Join-Path $repoRoot 'artifacts/desktop'
$appDirectory = Join-Path $artifactDirectory $application.directory
New-Item -ItemType Directory -Force -Path $appDirectory | Out-Null
Copy-Item -LiteralPath $binary -Destination (Join-Path $appDirectory $application.executable) -Force
$buildInfo = Join-Path $repoRoot "native/frontend/dist-$App/build-info.json"
$info = Get-Content -LiteralPath $buildInfo -Raw | ConvertFrom-Json
if ($info.variant -ne $App -or $info.version -ne $version) { throw 'Frontend variant or version does not match the selected app.' }
Copy-Item -LiteralPath $buildInfo -Destination $appDirectory -Force
foreach ($inputAsset in $inputs) {
    $outputFile = Join-Path $appDirectory ('resources/' + $inputAsset.RelativePath)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $outputFile) | Out-Null
    Copy-Item -LiteralPath $inputAsset.Path -Destination $outputFile -Force
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$zipPath = Join-Path $artifactDirectory "$($application.directory)-desktop.zip"
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
$zipStream = [System.IO.File]::Create($zipPath)
$zipArchive = [System.IO.Compression.ZipArchive]::new($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    Get-ChildItem -LiteralPath $appDirectory -File -Recurse | ForEach-Object {
        $entryName = $application.directory + '/' + $_.FullName.Substring($appDirectory.Length + 1).Replace('\','/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zipArchive, $_.FullName, $entryName, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally { $zipArchive.Dispose(); $zipStream.Dispose() }
Get-Item -LiteralPath (Join-Path $appDirectory $application.executable), $zipPath | Select-Object FullName,Length

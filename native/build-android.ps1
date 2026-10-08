param([switch]$SkipFrontend, [switch]$SkipRust)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$androidProject = Join-Path $repoRoot 'src-tauri/gen/android'
if (-not $env:JAVA_HOME) { $env:JAVA_HOME = 'C:/Program Files/Java/jdk-21' }
if (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android/Sdk' }
if (-not $env:NDK_HOME) {
    $ndkDirectory = Get-ChildItem -LiteralPath (Join-Path $env:ANDROID_HOME 'ndk') -Directory | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $ndkDirectory) { throw 'Install an Android NDK first.' }
    $env:NDK_HOME = $ndkDirectory.FullName
}
function Assert-NativeSuccess([string]$step) { if ($LASTEXITCODE -ne 0) { throw "$step failed with exit code $LASTEXITCODE" } }
Push-Location $repoRoot
try {
    if (-not $SkipFrontend) { & npm.cmd run build; Assert-NativeSuccess 'Frontend/assets build' }
    if (-not (Test-Path -LiteralPath (Join-Path $androidProject 'tauri.settings.gradle'))) {
        & npm.cmd run android:init; Assert-NativeSuccess 'Android initialization'
        $gradleFile = Join-Path $androidProject 'app/build.gradle.kts'
        $gradleSource = Get-Content -LiteralPath $gradleFile -Raw
        $gradleSource = $gradleSource -replace 'compileSdk = \d+', 'compileSdk = 36' -replace 'targetSdk = \d+', 'targetSdk = 36'
        [System.IO.File]::WriteAllText($gradleFile, $gradleSource)
    }
    $env:CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER = Join-Path $env:NDK_HOME 'toolchains/llvm/prebuilt/windows-x86_64/bin/aarch64-linux-android24-clang.cmd'
    $env:TAURI_ANDROID_PROJECT_PATH = $androidProject
    $env:WRY_ANDROID_PACKAGE = 'pt.tomaspedreira.worcalc'
    $env:WRY_ANDROID_LIBRARY = 'worcalc_app'
    $env:WRY_ANDROID_KOTLIN_FILES_OUT_DIR = Join-Path $androidProject 'app/src/main/java/pt/tomaspedreira/worcalc/generated'
    if (-not $SkipRust) { & cargo build -p worcalc-app --lib --release --target aarch64-linux-android --features custom-protocol; Assert-NativeSuccess 'Rust Android build' }

    # Explicit copies work on Windows without symbolic-link privileges.
    $jniDirectory = Join-Path $androidProject 'app/src/main/jniLibs/arm64-v8a'
    New-Item -ItemType Directory -Force -Path $jniDirectory | Out-Null
    Copy-Item -LiteralPath (Join-Path $repoRoot 'target/aarch64-linux-android/release/libworcalc_app.so') -Destination $jniDirectory -Force
    $assetDirectory = Join-Path $androidProject 'app/src/main/assets/resources'
    New-Item -ItemType Directory -Force -Path $assetDirectory | Out-Null
    Copy-Item -LiteralPath (Join-Path $repoRoot 'src-tauri/resources/catalog.json') -Destination $assetDirectory -Force
    foreach ($folder in @('maps', 'terrain')) {
        $destination = Join-Path $assetDirectory $folder
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        Get-ChildItem -LiteralPath (Join-Path $repoRoot "src-tauri/resources/$folder") -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
        }
    }

    $releaseConfig = Get-Content -LiteralPath (Join-Path $repoRoot 'src-tauri/tauri.conf.json') -Raw | ConvertFrom-Json
    $versionParts = $releaseConfig.version.Split('.')
    $androidVersionCode = [int]$versionParts[0] * 1000000 + [int]$versionParts[1] * 1000 + [int]$versionParts[2]
    $versionProperties = "tauri.android.versionName=$($releaseConfig.version)`ntauri.android.versionCode=$androidVersionCode`n"
    [System.IO.File]::WriteAllText((Join-Path $androidProject 'app/tauri.properties'), $versionProperties)
    Push-Location $androidProject
    try {
        & .\gradlew.bat :app:assembleUniversalRelease -PabiList=arm64-v8a -ParchList=arm64 -PtargetList=aarch64 -x rustBuildUniversalRelease --console=plain
        Assert-NativeSuccess 'APK assembly'
    } finally { Pop-Location }

    $artifactDirectory = Join-Path $repoRoot 'artifacts/android'
    New-Item -ItemType Directory -Force -Path $artifactDirectory | Out-Null
    $keystore = Join-Path $artifactDirectory 'worcalc-development.keystore'
    if (-not (Test-Path -LiteralPath $keystore)) {
        & (Join-Path $env:JAVA_HOME 'bin/keytool.exe') -genkeypair -keystore $keystore -storepass android -keypass android -alias worcalc-development -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=worCalc Development'
        Assert-NativeSuccess 'Development signing key'
    }
    $buildTools = Get-ChildItem -LiteralPath (Join-Path $env:ANDROID_HOME 'build-tools') -Directory | Sort-Object Name -Descending | Select-Object -First 1
    $unsigned = Join-Path $androidProject 'app/build/outputs/apk/universal/release/app-universal-release-unsigned.apk'
    $output = Join-Path $artifactDirectory 'worcalc-offline-arm64.apk'
    & (Join-Path $buildTools.FullName 'apksigner.bat') sign --ks $keystore --ks-key-alias worcalc-development --ks-pass pass:android --key-pass pass:android --out $output $unsigned
    Assert-NativeSuccess 'APK signing'
    & (Join-Path $buildTools.FullName 'apksigner.bat') verify $output
    Assert-NativeSuccess 'APK signature verification'
    Get-Item -LiteralPath $output | Select-Object FullName, Length
} finally { Pop-Location }

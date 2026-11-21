param(
    [ValidateSet('calculator','sketcher','kill-tracker')][string[]]$Apps = @('calculator','sketcher','kill-tracker'),
    [switch]$CreateShortcuts
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$applications = Get-Content -LiteralPath (Join-Path $repoRoot 'native/apps.json') -Raw | ConvertFrom-Json
Push-Location $repoRoot
try {
    foreach ($app in $Apps) {
        $application = $applications.$app
        & npm.cmd run tauri -- build --no-bundle --config $application.config --features $application.feature -- --no-default-features
        if ($LASTEXITCODE -ne 0) { throw "$($application.name) build failed with exit code $LASTEXITCODE" }
        & (Join-Path $PSScriptRoot 'package-desktop.ps1') -App $app
        if ($CreateShortcuts) {
            $directory = Join-Path $repoRoot "artifacts/desktop/$($application.directory)"
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) "$($application.name).lnk"))
            $shortcut.TargetPath = Join-Path $directory $application.executable
            $shortcut.WorkingDirectory = $directory
            $shortcut.Description = $application.name
            $shortcut.Save()
        }
    }
} finally { Pop-Location }

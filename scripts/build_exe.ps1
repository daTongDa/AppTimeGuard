# Build app_time_guard.exe and install package
param(
    [switch]$SkipInstallDeps,
    [switch]$NoInno
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> Workdir: $Root"

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    throw "python not found in PATH"
}

if (-not $SkipInstallDeps) {
    Write-Host "==> Installing deps..."
    python -m pip install -U pip
    python -m pip install -r requirements.txt
    python -m pip install -U "pyinstaller>=6.0"
}

$dist = Join-Path $Root "dist"
$build = Join-Path $Root "build"
$spec = Join-Path $Root "packaging\app_time_guard.spec"

if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Path $dist | Out-Null

Write-Host "==> PyInstaller..."
python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $build $spec

$exe = Join-Path $dist "app_time_guard.exe"
if (-not (Test-Path $exe)) {
    throw "Build failed: missing $exe"
}

$sizeMB = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "==> Built: $exe ($sizeMB MB)"

$pkg = Join-Path $dist "AppTimeGuard_Package"
New-Item -ItemType Directory -Path $pkg -Force | Out-Null
Copy-Item $exe (Join-Path $pkg "app_time_guard.exe") -Force

$installLines = @(
    '$ErrorActionPreference = "Stop"'
    '$Here = Split-Path -Parent $MyInvocation.MyCommand.Path'
    '$ExeSrc = Join-Path $Here "app_time_guard.exe"'
    '$Dest = Join-Path $env:LOCALAPPDATA "Programs\AppTimeGuard"'
    'New-Item -ItemType Directory -Path $Dest -Force | Out-Null'
    'Copy-Item $ExeSrc (Join-Path $Dest "app_time_guard.exe") -Force'
    '$Wsh = New-Object -ComObject WScript.Shell'
    '$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\App Time Guard"'
    'New-Item -ItemType Directory -Path $StartMenu -Force | Out-Null'
    '$lnk = $Wsh.CreateShortcut((Join-Path $StartMenu "App Time Guard.lnk"))'
    '$lnk.TargetPath = Join-Path $Dest "app_time_guard.exe"'
    '$lnk.WorkingDirectory = $Dest'
    '$lnk.Description = "App Time Guard"'
    '$lnk.Save()'
    '$Desktop = [Environment]::GetFolderPath("Desktop")'
    '$desk = $Wsh.CreateShortcut((Join-Path $Desktop "App Time Guard.lnk"))'
    '$desk.TargetPath = Join-Path $Dest "app_time_guard.exe"'
    '$desk.WorkingDirectory = $Dest'
    '$desk.Save()'
    'Write-Host "Installed to: $Dest"'
    '$ans = Read-Host "Start now? (Y/N)"'
    'if ($ans -match "^[Yy]") { Start-Process (Join-Path $Dest "app_time_guard.exe") }'
)
Set-Content -Path (Join-Path $pkg "install.ps1") -Value ($installLines -join "`r`n") -Encoding UTF8

$uninstallLines = @(
    '$ErrorActionPreference = "Stop"'
    '$Dest = Join-Path $env:LOCALAPPDATA "Programs\AppTimeGuard"'
    'Get-Process app_time_guard -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue'
    'if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force }'
    '$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\App Time Guard"'
    'if (Test-Path $StartMenu) { Remove-Item $StartMenu -Recurse -Force }'
    '$Desktop = [Environment]::GetFolderPath("Desktop")'
    '$desk = Join-Path $Desktop "App Time Guard.lnk"'
    'if (Test-Path $desk) { Remove-Item $desk -Force }'
    'Write-Host "Uninstalled program files and shortcuts."'
    'Write-Host "Data kept at: $env:LOCALAPPDATA\AppTimeGuard (delete manually if needed)"'
)
Set-Content -Path (Join-Path $pkg "uninstall.ps1") -Value ($uninstallLines -join "`r`n") -Encoding UTF8

$readmeLines = @(
    "App Time Guard Package"
    ""
    "Files:"
    "  app_time_guard.exe  - main program"
    "  install.ps1         - install for current user + shortcuts"
    "  uninstall.ps1       - uninstall"
    ""
    "Install:"
    "  powershell -ExecutionPolicy Bypass -File .\install.ps1"
    ""
    "UI: http://127.0.0.1:8765/"
    "Data: %LOCALAPPDATA%\AppTimeGuard\"
    ""
    "Or run app_time_guard.exe directly (portable)."
)
Set-Content -Path (Join-Path $pkg "README.txt") -Value ($readmeLines -join "`r`n") -Encoding UTF8

$zip = Join-Path $dist "AppTimeGuard_Portable.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $pkg "*") -DestinationPath $zip -Force
Write-Host "==> Zip: $zip"

if (-not $NoInno) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($iscc) {
        Write-Host "==> Inno Setup: $iscc"
        $outDir = Join-Path $dist "installer"
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
        & $iscc (Join-Path $Root "packaging\app_time_guard.iss")
        Get-ChildItem $outDir -Filter "*.exe" -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "==> Setup: $($_.FullName)"
        }
    } else {
        Write-Host "==> Inno Setup not found, skip Setup.exe (use zip package)"
    }
}

Write-Host ""
Write-Host "Done:"
Write-Host "  $exe"
Write-Host "  $zip"
Write-Host "  $pkg"

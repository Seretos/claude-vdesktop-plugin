# Build the vdesktop-plugin MCP server into a single-file Windows .exe.
#
# Usage (from plugin root):
#   pwsh -File scripts/build.ps1
#   pwsh -File scripts/build.ps1 -Clean      # remove dist/ build/ first
#   pwsh -File scripts/build.ps1 -Package    # also produce dist/vdesktop-plugin-<ver>.zip
#
# Requires: Python 3.11+ on PATH (via py.exe -3 launcher).
# Installs pyinstaller into the user-site or current env if missing.

[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$Package
)

$root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $root

# Note: do NOT set $ErrorActionPreference = "Stop" globally. PowerShell 5.1
# wraps native-command stderr as ErrorRecord, which trips Stop semantics for
# tools like PyInstaller that log heavily to stderr. We check $LASTEXITCODE
# after each native call instead.

function Write-Step($msg) {
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Fail($msg) {
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

# 1. Verify Python.
Write-Step "Checking Python"
$pythonOk = $false
try {
    $ver = & py -3 --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    $ver"
        $pythonOk = $true
    }
} catch { }
if (-not $pythonOk) {
    Fail "py.exe -3 not available. Install Python 3.11+ from https://www.python.org/downloads/ (be sure the 'py launcher' option is checked)."
}

# 2. Ensure plugin + build deps are installed.
Write-Step "Ensuring dependencies (plugin + pyinstaller)"
& py -3 -m pip install --quiet --disable-pip-version-check -e ".[build]"
if ($LASTEXITCODE -ne 0) {
    Fail "pip install failed."
}

# 3. Clean previous build artifacts if requested.
if ($Clean) {
    Write-Step "Cleaning dist/ and build/"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist, build
}

# 4. Run PyInstaller.
Write-Step "Running PyInstaller"
& py -3 -m PyInstaller vdesktop.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Fail "PyInstaller build failed."
}

$exe = Join-Path $root "dist\vdesktop.exe"
if (-not (Test-Path $exe)) {
    Fail "Expected dist/vdesktop.exe not produced."
}
$exeSize = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "    dist/vdesktop.exe (${exeSize} MB)"

# 5. Copy into bin/ where plugin.json expects it.
Write-Step "Copying to bin/vdesktop.exe"
New-Item -ItemType Directory -Force -Path "bin" | Out-Null
Copy-Item -Force $exe "bin/vdesktop.exe"

# 6. Smoke-test: MCP initialize handshake.
# PowerShell 5.1's Process StreamWriter prepends a UTF-8 BOM that MCP rejects.
# Work around it by staging the request in a temp file and using
# Start-Process -RedirectStandardInput, which pipes raw OS bytes.
Write-Step "Smoke-testing the binary (MCP initialize)"
$initMsg = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"build-smoke","version":"1"}}}'
$inFile = [System.IO.Path]::GetTempFileName()
$outFile = [System.IO.Path]::GetTempFileName()
$errFile = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllBytes($inFile, [System.Text.Encoding]::UTF8.GetBytes($initMsg + "`n"))
$proc = Start-Process -FilePath "bin\vdesktop.exe" `
    -RedirectStandardInput $inFile `
    -RedirectStandardOutput $outFile `
    -RedirectStandardError $errFile `
    -NoNewWindow -PassThru
if (-not $proc.WaitForExit(8000)) { $proc.Kill(); Start-Sleep -Milliseconds 200 }
$stdout = (Get-Content -Raw -ErrorAction SilentlyContinue $outFile)
$stderrText = (Get-Content -Raw -ErrorAction SilentlyContinue $errFile)
Remove-Item -ErrorAction SilentlyContinue $inFile, $outFile, $errFile
if ($stdout -match '"result"' -and $stdout -match '"protocolVersion"') {
    Write-Host "    handshake OK" -ForegroundColor Green
} else {
    Write-Host "    stdout: $stdout" -ForegroundColor Yellow
    Write-Host "    stderr: $stderrText" -ForegroundColor Yellow
    Fail "Handshake failed -- see output above."
}

# 7. Optional: produce a release zip.
if ($Package) {
    Write-Step "Packaging release zip"
    $version = (Select-String -Path ".claude-plugin/plugin.json" -Pattern '"version"\s*:\s*"([^"]+)"').Matches[0].Groups[1].Value
    $zipName = "vdesktop-plugin-$version.zip"
    $zipPath = Join-Path $root "dist\$zipName"
    if (Test-Path $zipPath) { Remove-Item $zipPath }
    $stage = Join-Path $root "build\stage\vdesktop-plugin"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $root "build\stage")
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Copy-Item -Recurse -Force ".claude-plugin" $stage
    Copy-Item -Recurse -Force "bin" $stage
    Copy-Item -Recurse -Force "skills" $stage
    Copy-Item -Force "README.md", "LICENSE" $stage -ErrorAction SilentlyContinue
    Compress-Archive -Path "$stage\*" -DestinationPath $zipPath -Force
    $zipSize = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)
    Write-Host "    dist/$zipName (${zipSize} MB)"
}

Write-Step "Done."
Write-Host "bin/vdesktop.exe is ready. Plugin manifest already points at it."

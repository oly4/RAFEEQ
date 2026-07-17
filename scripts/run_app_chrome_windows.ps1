param(
    [int]$BackendPort = 8000,
    [string]$BackendHost = "127.0.0.1",
    [switch]$RemoteBackend
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RunDir = Join-Path $RepoRoot ".run"
$MobileDir = Join-Path $RepoRoot "apps\mobile"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

function Test-HttpOk([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-HttpOk([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpOk $Url) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

Set-Location $RepoRoot

$UseRemoteBackend = $RemoteBackend -or ($BackendHost -ne "127.0.0.1" -and $BackendHost -ne "localhost")
$BackendHealthHost = if ($UseRemoteBackend) { $BackendHost } else { "127.0.0.1" }
$BackendHealthUrl = "http://$BackendHealthHost`:$BackendPort/health/ready"
$BackendApiUrl = "http://$BackendHost`:$BackendPort/api/v1"
$BackendWsUrl = "ws://$BackendHost`:$BackendPort"

if (-not (Test-HttpOk $BackendHealthUrl)) {
    if ($UseRemoteBackend) {
        throw "Remote RAFEEQ backend is not reachable at $BackendHealthUrl. Make sure the Raspberry Pi backend is running and both devices are on the same network."
    }
    Write-Host "Starting RAFEEQ backend on port $BackendPort..."
    $BackendPython = Join-Path $RepoRoot "services\backend\.venv\Scripts\python.exe"
    if (-not (Test-Path $BackendPython)) {
        throw "Backend virtual environment not found: $BackendPython"
    }
    Start-Process `
        -FilePath $BackendPython `
        -ArgumentList @("-m", "uvicorn", "rafeeq_backend.main:app", "--host", "0.0.0.0", "--port", "$BackendPort") `
        -WorkingDirectory (Join-Path $RepoRoot "services\backend") `
        -RedirectStandardOutput (Join-Path $RunDir "backend.out.log") `
        -RedirectStandardError (Join-Path $RunDir "backend.err.log") `
        -WindowStyle Hidden

    if (-not (Wait-HttpOk $BackendHealthUrl 45)) {
        throw "Backend did not become ready. Check .run\backend.err.log"
    }
} else {
    if ($UseRemoteBackend) {
        Write-Host "Remote backend is reachable: $BackendHealthUrl"
    } else {
        Write-Host "Backend already running."
    }
}

$Flutter = "C:\flutter\bin\flutter.bat"
if (-not (Test-Path $Flutter)) {
    $Flutter = "flutter"
}

Write-Host "Starting RAFEEQ directly in Google Chrome..."
Write-Host "Keep this window open while testing. Press q here to stop Flutter."
Write-Host ""
Write-Host "Family: caregiver@demo.rafeeq.app / Rafeeq-Test-2026!"
Write-Host "Doctor: doctor@demo.rafeeq.app / Rafeeq-Test-2026!"
Write-Host ""

Set-Location $MobileDir
& $Flutter pub get
& $Flutter run `
    -d chrome `
    --dart-define=API_BASE_URL=$BackendApiUrl `
    --dart-define=WS_BASE_URL=$BackendWsUrl

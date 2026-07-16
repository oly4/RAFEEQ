param(
    [int]$BackendPort = 8000,
    [int]$WebPort = 8080,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RunDir = Join-Path $RepoRoot ".run"
$MobileDir = Join-Path $RepoRoot "apps\mobile"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

function Get-RafeeqLanIp {
    try {
        $ip = Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object {
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.PrefixOrigin -ne "WellKnown"
            } |
            Select-Object -First 1 -ExpandProperty IPAddress
        if ($ip) { return $ip }
    } catch {
        # Fall back below when Get-NetIPAddress is unavailable.
    }
    return "127.0.0.1"
}

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

function Stop-PortListener([int]$Port) {
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    $processIds = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        if ($processId -and $processId -ne $PID) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

Set-Location $RepoRoot

$LanIp = Get-RafeeqLanIp
$BackendHealthUrl = "http://127.0.0.1:$BackendPort/health/ready"
$BackendApiUrl = "http://$LanIp`:$BackendPort/api/v1"
$BackendWsUrl = "ws://$LanIp`:$BackendPort"
$AppUrl = "http://127.0.0.1:$WebPort"
$BuildDir = Join-Path $MobileDir "build\web"

if (-not (Test-HttpOk $BackendHealthUrl)) {
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
    Write-Host "Backend already running."
}

if (-not $SkipBuild -or -not (Test-Path (Join-Path $BuildDir "index.html"))) {
    Write-Host "Building RAFEEQ Flutter web app..."
    $Flutter = "C:\flutter\bin\flutter.bat"
    if (-not (Test-Path $Flutter)) {
        $Flutter = "flutter"
    }
    Push-Location $MobileDir
    try {
        & $Flutter pub get
        if ($LASTEXITCODE -ne 0) { throw "flutter pub get failed." }
        & $Flutter build web --no-wasm-dry-run --dart-define=API_BASE_URL=$BackendApiUrl --dart-define=WS_BASE_URL=$BackendWsUrl
        if ($LASTEXITCODE -ne 0) { throw "flutter build web failed." }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "Using existing Flutter web build."
}

if (-not (Test-Path (Join-Path $BuildDir "index.html"))) {
    throw "Flutter web build was not found at $BuildDir"
}

if (-not (Test-HttpOk $AppUrl)) {
    Stop-PortListener $WebPort
    Write-Host "Serving RAFEEQ web app on port $WebPort..."
    $Python = "python"
    $ServerCommand = @"
cd "$BuildDir"
& "$Python" -m http.server $WebPort --bind 0.0.0.0
"@
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $ServerCommand) `
        -WorkingDirectory $BuildDir

    if (-not (Wait-HttpOk $AppUrl 45)) {
        throw "Web app server did not start on $AppUrl."
    }
} else {
    Write-Host "Web app already running."
}

Start-Process $AppUrl

Write-Host ""
Write-Host "RAFEEQ is ready."
Write-Host "App:      $AppUrl"
Write-Host "Backend:  $BackendHealthUrl"
Write-Host "LAN app:  http://$LanIp`:$WebPort"
Write-Host ""
Write-Host "Family account:"
Write-Host "  Email:    rafeeq.family.test@example.com"
Write-Host "  Password: Rafeeq-Test-2026!"
Write-Host ""
Write-Host "Doctor account:"
Write-Host "  Email:    rafeeq.doctor.test@example.com"
Write-Host "  Password: Rafeeq-Test-2026!"

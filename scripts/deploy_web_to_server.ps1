param(
    [Parameter(Mandatory = $true)]
    [string]$ServerHost,

    [string]$ServerUser = "root",

    [int]$BackendPort = 8000,

    [int]$WebPort = 80,

    [string]$CameraStreamUrl = "",

    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$MobileDir = Join-Path $RepoRoot "apps\mobile"
$BuildDir = Join-Path $MobileDir "build\web"
$RunDir = Join-Path $RepoRoot ".run"
$ArchivePath = Join-Path $RunDir "rafeeq-web.tar.gz"
$target = "$ServerUser@$ServerHost"
$sshOptions = @("-o", "StrictHostKeyChecking=accept-new")

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

if (-not $SkipBuild) {
    $Flutter = "C:\flutter\bin\flutter.bat"
    if (-not (Test-Path $Flutter)) {
        $Flutter = "flutter"
    }

    Push-Location $MobileDir
    try {
        & $Flutter pub get
        if ($LASTEXITCODE -ne 0) { throw "flutter pub get failed." }

        & $Flutter build web --no-wasm-dry-run `
            --dart-define=API_BASE_URL=http://$ServerHost`:$BackendPort/api/v1 `
            --dart-define=WS_BASE_URL=ws://$ServerHost`:$BackendPort `
            --dart-define=RAFEEQ_CAMERA_STREAM_URL=$CameraStreamUrl
        if ($LASTEXITCODE -ne 0) { throw "flutter build web failed." }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $BuildDir "index.html"))) {
    throw "Flutter web build not found. Build directory: $BuildDir"
}

if (Test-Path $ArchivePath) {
    Remove-Item -LiteralPath $ArchivePath -Force
}

tar -czf $ArchivePath -C $BuildDir .
if ($LASTEXITCODE -ne 0) { throw "Failed to create web archive." }

Write-Host "Uploading RAFEEQ web app to $target..."
scp @sshOptions $ArchivePath "$target`:/tmp/rafeeq-web.tar.gz"

Write-Host "Starting nginx web container on port $WebPort..."
ssh @sshOptions $target @"
set -e
mkdir -p /opt/rafeeq-web
rm -rf /opt/rafeeq-web/*
tar -xzf /tmp/rafeeq-web.tar.gz -C /opt/rafeeq-web
ufw allow $WebPort/tcp
docker rm -f rafeeq-web >/dev/null 2>&1 || true
docker run -d --restart unless-stopped --name rafeeq-web -p $WebPort`:80 -v /opt/rafeeq-web:/usr/share/nginx/html:ro nginx:alpine
docker ps --filter name=rafeeq-web
"@

Write-Host ""
Write-Host "RAFEEQ web app deployed:"
Write-Host "  http://$ServerHost"
Write-Host ""
Write-Host "Backend:"
Write-Host "  http://$ServerHost`:$BackendPort/health/ready"

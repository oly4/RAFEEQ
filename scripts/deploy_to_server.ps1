param(
    [Parameter(Mandatory = $true)]
    [string]$ServerHost,

    [string]$ServerUser = "root",

    [string]$RepoUrl = "https://github.com/oly4/RAFEEQ.git",

    [string]$RemoteDir = "/opt/rafeeq",

    [string]$EnvFile = ".env.production"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    throw "Missing $EnvFile. Run scripts\prepare_deployment_env.ps1 first."
}

$target = "$ServerUser@$ServerHost"

Write-Host "Installing server dependencies on $target..."
ssh $target @"
set -e
apt-get update
apt-get install -y ca-certificates curl git ufw
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.asc ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi
. /etc/os-release
echo "deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
ufw allow OpenSSH
ufw allow 8000/tcp
ufw allow 1883/tcp
ufw --force enable
if [ ! -d "$RemoteDir/.git" ]; then
  mkdir -p "$RemoteDir"
  git clone "$RepoUrl" "$RemoteDir"
else
  git -C "$RemoteDir" fetch origin
  git -C "$RemoteDir" reset --hard origin/main
fi
"@

Write-Host "Uploading production environment..."
scp $EnvFile "$target`:$RemoteDir/.env.production"

Write-Host "Starting RAFEEQ backend stack..."
ssh $target @"
set -e
cd "$RemoteDir"
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
"@

Write-Host ""
Write-Host "Checking backend health..."
try {
    $health = Invoke-WebRequest -Uri "http://$ServerHost`:8000/health/ready" -UseBasicParsing -TimeoutSec 10
    Write-Host $health.Content
} catch {
    Write-Host "Backend started, but health check from laptop failed. Check firewall/network, then try:"
    Write-Host "  http://$ServerHost`:8000/health/ready"
}

Write-Host ""
Write-Host "If health is ready, run the web app from your laptop:"
Write-Host "  .\scripts\run_app_windows.ps1 -BackendHost $ServerHost -RemoteBackend"

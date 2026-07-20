param(
    [Parameter(Mandatory = $true)]
    [string]$ServerHost,

    [string]$OutputPath = ".env.production",

    [string]$AppPort = "8000",

    [string]$OpenAiApiKey = ""
)

$ErrorActionPreference = "Stop"

function New-RandomSecret([int]$Bytes = 48) {
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($buffer)
    } finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($buffer)
}

function New-RandomHex([int]$Bytes = 32) {
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($buffer)
    } finally {
        $rng.Dispose()
    }
    return -join ($buffer | ForEach-Object { $_.ToString("x2") })
}

$postgresPassword = New-RandomHex 24
$jwtAccessSecret = New-RandomSecret 64
$jwtRefreshSecret = New-RandomSecret 64
$deviceSecret = New-RandomHex 32

$content = @"
APP_ENV=production
APP_BASE_URL=http://$ServerHost`:$AppPort
POSTGRES_PASSWORD=$postgresPassword
DATABASE_URL=postgresql+psycopg://rafeeq:$postgresPassword@postgres:5432/rafeeq
REDIS_URL=redis://redis:6379/0
JWT_ACCESS_SECRET=$jwtAccessSecret
JWT_REFRESH_SECRET=$jwtRefreshSecret
JWT_ACCESS_TTL_MINUTES=15
JWT_REFRESH_TTL_DAYS=30
MQTT_HOST=mosquitto
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
FCM_PROJECT_ID=
FCM_CREDENTIALS_PATH=
OBJECT_STORAGE_ENDPOINT=
OBJECT_STORAGE_BUCKET=
OBJECT_STORAGE_ACCESS_KEY=
OBJECT_STORAGE_SECRET_KEY=
CORS_ALLOWED_ORIGINS=http://127.0.0.1:8080,http://localhost:8080,http://$ServerHost,http://$ServerHost`:8080
LOG_LEVEL=INFO
OPENAI_API_KEY=$OpenAiApiKey
OPENAI_TEXT_MODEL=gpt-5.4-nano
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=alloy
DEMO_CAREGIVER_PASSWORD=Rafeeq-Test-2026!
DEMO_DOCTOR_PASSWORD=Rafeeq-Test-2026!
DEMO_DEVICE_SECRET=$deviceSecret
"@

$resolvedOutput = Join-Path (Resolve-Path ".") $OutputPath
$content | Set-Content -Path $resolvedOutput -Encoding UTF8

Write-Host "Created $resolvedOutput"
Write-Host "Keep this file private. Do not commit it."
Write-Host ""
Write-Host "Next:"
Write-Host "  .\scripts\deploy_to_server.ps1 -ServerHost $ServerHost -EnvFile $OutputPath"

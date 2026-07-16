param(
    [Parameter(Mandatory = $true)]
    [string]$LanIp
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tlsDir = Join-Path $root '.run\tls'
$webBuild = Join-Path $root 'apps\mobile\build\web'
$opensslCandidates = @(
    'C:\Program Files\Git\usr\bin\openssl.exe',
    'C:\Program Files\Git\mingw64\bin\openssl.exe'
)
$openssl = $opensslCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $openssl) {
    throw 'OpenSSL was not found. Install Git for Windows or OpenSSL first.'
}

New-Item -ItemType Directory -Force -Path $tlsDir | Out-Null
$caKey = Join-Path $tlsDir 'rafeeq-dev-ca.key'
$caCert = Join-Path $tlsDir 'rafeeq-dev-ca.crt'
$serverKey = Join-Path $tlsDir 'rafeeq-local.key'
$serverCsr = Join-Path $tlsDir 'rafeeq-local.csr'
$serverCert = Join-Path $tlsDir 'rafeeq-local.crt'
$extensions = Join-Path $tlsDir 'rafeeq-local.ext'

@"
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=@alt_names

[alt_names]
IP.1=$LanIp
IP.2=127.0.0.1
DNS.1=localhost
DNS.2=$env:COMPUTERNAME
"@ | Set-Content -Encoding ascii -LiteralPath $extensions

& $openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out $caKey
& $openssl req -x509 -new -key $caKey -sha256 -days 3650 -out $caCert `
    -subj '/CN=RAFEEQ Local Development CA/O=RAFEEQ Development'
& $openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out $serverKey
& $openssl req -new -key $serverKey -out $serverCsr `
    -subj "/CN=$LanIp/O=RAFEEQ Development"
& $openssl x509 -req -in $serverCsr -CA $caCert -CAkey $caKey -CAcreateserial `
    -out $serverCert -days 825 -sha256 -extfile $extensions
& $openssl x509 -in $caCert -outform DER -out (Join-Path $tlsDir 'rafeeq-dev-ca.cer')

if (Test-Path $webBuild) {
    Copy-Item -Force (Join-Path $tlsDir 'rafeeq-dev-ca.cer') `
        (Join-Path $webBuild 'rafeeq-dev-ca.cer')
}

Write-Output "TLS certificate created for $LanIp in $tlsDir"

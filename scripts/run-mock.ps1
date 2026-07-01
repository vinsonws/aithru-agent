param(
  [string]$PlatformRoot = (Join-Path $PSScriptRoot "..\..\aithru-platform"),
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [int]$MockPort = 19000
)

$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$MockHostDir = Join-Path $PlatformRoot "tools\platform-mock-host"
$MockUrl = "http://localhost:$MockPort"
$FrontendUrl = "http://localhost:$FrontendPort"
$BackendUrl = "http://127.0.0.1:$BackendPort"

if (-not (Test-Path (Join-Path $MockHostDir "package.json"))) {
  throw "Cannot find platform mock host at $MockHostDir"
}

$jobs = @()

try {
  $jobs += Start-Job -Name "aithru-agent-mock" -ArgumentList $MockHostDir,$RootDir,$MockPort,$FrontendUrl -ScriptBlock {
    param($MockHostDir,$RootDir,$MockPort,$FrontendUrl)
    Set-Location $MockHostDir
    if (-not (Test-Path "node_modules")) {
      npm ci
    }
    npx tsx src/cli.ts host --config "$RootDir\aithru.mock.yml" --port $MockPort --app-url $FrontendUrl --origin $FrontendUrl
  }

  $jobs += Start-Job -Name "aithru-agent-backend" -ArgumentList $RootDir,$BackendPort,$MockUrl,$FrontendUrl,$BackendUrl -ScriptBlock {
    param($RootDir,$BackendPort,$MockUrl,$FrontendUrl,$BackendUrl)
    Set-Location "$RootDir\backend"
    $env:HOST = "127.0.0.1"
    $env:PORT = "$BackendPort"
    $env:AITHRU_PLATFORM_AUTH_ENABLED = "true"
    $env:AITHRU_PLATFORM_URL = $MockUrl
    $env:AITHRU_ISSUER = $MockUrl
    $env:AITHRU_APP_KEY = "agent"
    $env:AITHRU_CLIENT_SECRET = "agent-mock-secret"
    $env:AITHRU_PUBLIC_BASE_URL = $FrontendUrl
    $env:AITHRU_API_BASE_URL = "$FrontendUrl/api"
    $env:AITHRU_INTERNAL_BASE_URL = "$BackendUrl/api"
    $env:AITHRU_HEALTH_URL = "$BackendUrl/api/health"
    $env:AITHRU_FAIL_ON_REGISTRATION_ERROR = "false"
    $env:AITHRU_LIFECYCLE_ENABLED = "false"
    $env:AITHRU_HEARTBEAT_ENABLED = "false"
    npm run dev
  }

  $jobs += Start-Job -Name "aithru-agent-frontend" -ArgumentList $RootDir,$BackendUrl,$FrontendPort -ScriptBlock {
    param($RootDir,$BackendUrl,$FrontendPort)
    Set-Location "$RootDir\frontend"
    $env:AITHRU_AGENT_BACKEND = $BackendUrl
    $env:VITE_AITHRU_APP_KEY = "agent"
    npm run dev -- --host 127.0.0.1 --port $FrontendPort --strictPort
  }

  Write-Host "Open $MockUrl/apps/agent"
  Wait-Job -Any $jobs | Receive-Job
} finally {
  foreach ($job in $jobs) {
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force -ErrorAction SilentlyContinue
  }
}

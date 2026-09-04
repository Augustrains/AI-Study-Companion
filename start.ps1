[CmdletBinding()]
param(
    # Optional database user ID used to print the matching frontend URL.
    [int]$UserId = 0
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$frontendRoot = Join-Path $projectRoot "front\frontend"
$runtimeDirectory = Join-Path $projectRoot ".runtime"
$backendLog = Join-Path $runtimeDirectory "backend.log"
$frontendLog = Join-Path $runtimeDirectory "frontend.log"

function Test-LocalPort {
    param([int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $client.Connect("127.0.0.1", $Port)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Start-HiddenPowerShell {
    param([string]$WorkingDirectory, [string]$Command)
    $safeDirectory = $WorkingDirectory.Replace("'", "''")
    Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", "Set-Location -LiteralPath '$safeDirectory'; $Command"
    ) | Out-Null
}

if (-not (Test-Path -LiteralPath $frontendRoot)) {
    throw "Frontend directory does not exist: $frontendRoot"
}

$backendPort = 8001
$backendRunning = Test-LocalPort -Port $backendPort
$frontendRunning = Test-LocalPort -Port 5173

if (-not $backendRunning -or -not $frontendRunning) {
    New-Item -ItemType Directory -Force -Path $runtimeDirectory | Out-Null
}

if (-not $backendRunning) {
    Set-Content -LiteralPath $backendLog -Value ""
    Start-HiddenPowerShell -WorkingDirectory $projectRoot -Command "python -m uvicorn api.asgi:app --host 127.0.0.1 --port $backendPort *>> '$backendLog'"
    Write-Host "Starting backend: http://127.0.0.1:$backendPort"
}

if (-not $frontendRunning) {
    Set-Content -LiteralPath $frontendLog -Value ""
    Start-HiddenPowerShell -WorkingDirectory $frontendRoot -Command "`$env:VITE_API_BASE_URL='http://127.0.0.1:$backendPort/api'; npm.cmd run dev -- --host 127.0.0.1 --port 5173 *>> '$frontendLog'"
    Write-Host "Starting frontend: http://127.0.0.1:5173"
}

for ($attempt = 0; $attempt -lt 10; $attempt++) {
    if ((Test-LocalPort -Port $backendPort) -and (Test-LocalPort -Port 5173)) {
        break
    }
    Start-Sleep -Seconds 2
}

if ((Test-LocalPort -Port $backendPort) -and (Test-LocalPort -Port 5173)) {
    Write-Host "Backend is running: http://127.0.0.1:$backendPort"
    Write-Host "Frontend is running: http://127.0.0.1:5173"
} else {
    Write-Warning "Startup is not ready yet. Check: $backendLog and $frontendLog"
}

$url = "http://127.0.0.1:5173"
if ($UserId -gt 0) {
    $url = "$url/?user_id=$UserId"
}
Write-Host "Open after startup: $url"
Write-Host "First startup may take a few seconds. Use the same numeric user ID as the learner profile."

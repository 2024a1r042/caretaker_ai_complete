# CareTaker.ai — start backend (port 8000) + frontend (port 5500) and open the app.
# Usage:  .\run_windows.ps1
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$vpy = "$backend\venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) { Write-Host "Run .\setup_windows.ps1 first." -ForegroundColor Red; exit 1 }

# stop anything already on our ports
$conns = Get-NetTCPConnection -LocalPort 8000, 5500 -State Listen -ErrorAction SilentlyContinue
if ($conns) { Stop-Process -Id ($conns.OwningProcess | Sort-Object -Unique) -Force -ErrorAction SilentlyContinue; Start-Sleep 1 }

Write-Host "Starting backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
Start-Process -FilePath $vpy -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $backend

Write-Host "Starting frontend on http://127.0.0.1:5500 ..." -ForegroundColor Cyan
Start-Process -FilePath $vpy -ArgumentList "-m", "http.server", "5500", "--bind", "127.0.0.1" -WorkingDirectory $frontend

Write-Host "Waiting for the backend (first start loads the AI models, ~30 s)..."
for ($i = 0; $i -lt 90; $i++) {
    try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/ -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 2 }
}
try {
    $h = Invoke-RestMethod http://127.0.0.1:8000/api/health/ai -TimeoutSec 5
    Write-Host "`nAI health:" -ForegroundColor Cyan
    $h.advice | ForEach-Object { Write-Host "  - $_" }
} catch {}

# Always use 127.0.0.1 (not localhost): the two keep separate logins in the browser.
Start-Process "http://127.0.0.1:5500/login.html"
Write-Host "`nOpened http://127.0.0.1:5500/login.html" -ForegroundColor Green

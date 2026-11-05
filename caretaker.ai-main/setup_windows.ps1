# CareTaker.ai — one-time setup on Windows.
# Run from the project folder in PowerShell:   .\setup_windows.ps1
# (If scripts are blocked:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"

Write-Host "`n[1/4] Finding Python 3.11 (3.10 also works)..." -ForegroundColor Cyan
$py = $null
foreach ($v in @("3.11", "3.10")) {
    try { & py "-$v" -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $py = @("py", "-$v"); break } } catch {}
}
if (-not $py) {
    Write-Host "Python 3.11 not found. Install it from https://www.python.org/downloads/release/python-3119/ (tick 'Add to PATH'), then re-run." -ForegroundColor Red
    exit 1
}

Write-Host "[2/4] Creating backend\venv ..." -ForegroundColor Cyan
if (-not (Test-Path "$backend\venv")) { & $py[0] $py[1] -m venv "$backend\venv" }
$vpy = "$backend\venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip | Out-Null

Write-Host "[3/4] Installing packages (first time: ~10 min, PyTorch is large)..." -ForegroundColor Cyan
& $vpy -m pip install -r "$backend\requirements-windows-py311.lock.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Locked install failed — trying the unpinned list..." -ForegroundColor Yellow
    & $vpy -m pip install -r "$backend\requirements.txt"
}

Write-Host "[4/4] Preparing backend\.env ..." -ForegroundColor Cyan
if (-not (Test-Path "$backend\.env")) {
    Copy-Item "$backend\.env.example" "$backend\.env"
    # quick-start: SQLite works out of the box; switch to PostgreSQL for real use
    (Get-Content "$backend\.env") `
        -replace '^DATABASE_URL=.*', 'DATABASE_URL=sqlite:///./caretaker_demo.db' `
        -replace '^SECRET_KEY=.*', ("SECRET_KEY=" + [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")) |
        Set-Content "$backend\.env"
    Write-Host "Created backend\.env (SQLite quick-start). Put your GEMINI_API_KEY in it for full Saathi conversations." -ForegroundColor Yellow
}

Write-Host "`nDone. Start everything with:  .\run_windows.ps1" -ForegroundColor Green

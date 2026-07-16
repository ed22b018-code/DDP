# =============================================================================
# run_dev.ps1 -- Windows PowerShell one-command launcher.
# =============================================================================
# Usage (from the project root):
#     powershell -ExecutionPolicy Bypass -File scripts\run_dev.ps1
#
# Opens the backend and the dashboard, EACH IN ITS OWN new PowerShell window
# that stays open (so you can see logs and any errors). Close those windows to
# stop the servers. The dashboard opens in your browser automatically.
# =============================================================================

$ErrorActionPreference = "Stop"

# Project root = the folder above this scripts\ folder.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

# --- Find the venv Python --------------------------------------------------
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "!! No virtual environment found. Create one first:" -ForegroundColor Yellow
    Write-Host "     python -m venv .venv"
    Write-Host "     .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# --- Check Node/npm is available -------------------------------------------
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    Write-Host "!! 'npm' was not found on your PATH. Install Node.js 18+ from https://nodejs.org" -ForegroundColor Yellow
    exit 1
}

# --- Train the model if it doesn't exist yet -------------------------------
if (-not (Test-Path (Join-Path $Root "ml\artifacts\model.joblib"))) {
    Write-Host ">> No trained model found. Training on synthetic data..." -ForegroundColor Cyan
    & $Python ml\train.py
}

# --- Install frontend deps on first run ------------------------------------
$FrontendDir = Join-Path $Root "frontend"
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host ">> Installing frontend dependencies (first run only)..." -ForegroundColor Cyan
    Push-Location $FrontendDir
    npm install
    Pop-Location
}

# --- Start the backend in its own window -----------------------------------
Write-Host ">> Starting backend  -> http://127.0.0.1:8000" -ForegroundColor Green
$backendCmd = "Set-Location '$Root'; & '$Python' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $backendCmd

# --- Start the frontend in its own window ----------------------------------
Write-Host ">> Starting dashboard -> http://localhost:5173" -ForegroundColor Green
# Use cmd.exe /k so npm.cmd resolves reliably and the window stays open.
$frontendCmd = "cd /d `"$FrontendDir`" && npm run dev"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $frontendCmd

# --- Give the dev server a moment, then open the browser -------------------
Start-Sleep -Seconds 5
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Backend  : http://127.0.0.1:8000  (API docs at /docs)"
Write-Host "  Dashboard: http://localhost:5173"
Write-Host ""
Write-Host "  Two new windows opened (backend + dashboard)."
Write-Host "  Close those windows to stop the servers."
Write-Host "============================================================" -ForegroundColor Green

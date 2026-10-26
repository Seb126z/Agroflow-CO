# Ejecuta el pipeline completo de AgroFlow-CO (las 4 fuentes mayoristas)
# y escribe un log con fecha. Pensado para Task Scheduler (RF-10).
#
# Registrar como tarea programada (PowerShell, una sola vez):
#
#   schtasks /create /tn "AgroFlow-CO Pipeline" /sc DAILY /st 03:00 `
#     /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"C:\Users\cnseb\3D Objects\AgroFlow-CO\scripts\run_pipeline.ps1`""
#
# Quitarla:
#   schtasks /delete /tn "AgroFlow-CO Pipeline" /f

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "data\processed\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("run_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

Set-Location $ProjectRoot
& $Python -m src.agroflow.cli extract --all *>> $LogFile
$exitCode = $LASTEXITCODE
Write-Output "AgroFlow-CO pipeline terminó con código $exitCode. Log: $LogFile"
exit $exitCode

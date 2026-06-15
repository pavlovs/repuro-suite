# start_cockpit.ps1 - idempotent: starts the cockpit server detached if not already listening.
# Launched by Startup-folder RepuroCockpit.cmd at logon; safe to run any time. ASCII only (PS 5.1 no-BOM).
$port = 8099
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$listening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listening) { Write-Output "cockpit already on :$port (PID $($listening[0].OwningProcess))"; exit 0 }
$py = Join-Path $root ".venv\Scripts\python.exe"
Start-Process -FilePath $py -ArgumentList "cockpit.py serve --port $port" -WorkingDirectory $root -WindowStyle Hidden
$ok = $false
foreach ($i in 1..6) {
  Start-Sleep -Seconds 2
  try { $health = Invoke-RestMethod "http://127.0.0.1:$port/api/health" -TimeoutSec 5; $ok = ($health.status -eq "ok"); if ($ok) { break } } catch {}
}
if ($ok) { Write-Output "cockpit started on :$port" } else { Write-Output "cockpit start FAILED"; exit 1 }

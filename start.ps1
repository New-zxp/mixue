param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = (Get-Command python -ErrorAction Stop).Source
try {
    $taskResponse = Invoke-WebRequest -Uri 'http://127.0.0.1:8877/api/status' -TimeoutSec 2 -UseBasicParsing
    if ($taskResponse.StatusCode -eq 200) {
        if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8877/' }
        Write-Output 'Tea Atlas is already running: http://127.0.0.1:8877/'
        exit 0
    }
} catch {}
$taskLogDir = Join-Path $PSScriptRoot 'work'
New-Item -ItemType Directory -Path $taskLogDir -Force | Out-Null
$taskAppPath = Join-Path $PSScriptRoot 'app.py'
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList "`"$taskAppPath`"" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskLogDir 'server.out.log') -RedirectStandardError (Join-Path $taskLogDir 'server.err.log')
$taskProcess.Id | Set-Content -LiteralPath (Join-Path $taskLogDir 'server.pid')
@{ id=$taskProcess.Id; started=$taskProcess.StartTime.ToUniversalTime().ToString('o'); app=$taskAppPath } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskLogDir 'server-process.json')
for ($taskAttempt=0; $taskAttempt -lt 30; $taskAttempt++) {
    $taskProcess.Refresh()
    if ($taskProcess.HasExited) { throw 'Server exited. See work/server.err.log.' }
    try { $taskReady = Invoke-WebRequest -Uri 'http://127.0.0.1:8877/api/status' -TimeoutSec 1 -UseBasicParsing } catch { $taskReady = $null }
    if ($taskReady.StatusCode -eq 200) {
        Write-Output "Tea Atlas ready (PID $($taskProcess.Id)): http://127.0.0.1:8877/"
        if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8877/' }
        exit 0
    }
    Start-Sleep -Milliseconds 500
}
throw 'Server readiness timed out. See work/server.err.log.'

$ErrorActionPreference = 'Stop'
$taskRecord = Join-Path $PSScriptRoot 'work/server-process.json'
if (-not (Test-Path -LiteralPath $taskRecord)) { Write-Output 'No managed server record.'; exit 0 }
$taskInfo = Get-Content -LiteralPath $taskRecord -Raw | ConvertFrom-Json
$taskProcess = Get-Process -Id $taskInfo.id -ErrorAction SilentlyContinue
if (-not $taskProcess) { Write-Output 'Server already stopped.'; exit 0 }
$taskExpected = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'app.py'))
$taskDetails = Get-CimInstance Win32_Process -Filter "ProcessId=$($taskInfo.id)"
if ($taskInfo.app -ne $taskExpected -or [Math]::Abs(($taskProcess.StartTime.ToUniversalTime() - ([datetime]$taskInfo.started).ToUniversalTime()).TotalMilliseconds) -gt 1 -or -not $taskDetails.CommandLine.Contains($taskExpected)) { throw 'Process identity changed; refusing to stop another process.' }
Stop-Process -Id $taskInfo.id
Write-Output 'Tea Atlas stopped. Interrupted collections can be resumed after restart.'

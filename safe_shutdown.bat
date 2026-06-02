@echo off
setlocal

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

pushd "%ROOT%" >nul 2>nul
if errorlevel 1 (
  echo Cannot enter project directory: %ROOT%
  pause
  exit /b 1
)

echo [Mir2Auto] Safe shutdown from:
echo %CD%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root=(Get-Location).Path;" ^
  "$projectScripts=@((Join-Path $root 'py\app.py'));" ^
  "function Test-ProjectCommandLine($commandLine) { " ^
  "  if (-not $commandLine) { return $false } " ^
  "  $slashCommand=$commandLine -replace '\\','/'; " ^
  "  foreach ($path in $projectScripts) { " ^
  "    $slashPath=$path -replace '\\','/'; " ^
  "    if ($commandLine -like ('*' + $path + '*') -or $slashCommand -like ('*' + $slashPath + '*')) { return $true } " ^
  "  } " ^
  "  foreach ($marker in @('py/app.py')) { " ^
  "    if ($slashCommand -like ('*' + $marker + '*')) { return $true } " ^
  "  } " ^
  "  return $false " ^
  "} " ^
  "function Test-ProjectProcess($process) { " ^
  "  if ($process.Name -ne 'python.exe' -and $process.Name -ne 'pythonw.exe') { return $false } " ^
  "  return (Test-ProjectCommandLine $process.CommandLine) " ^
  "} " ^
  "function Get-ProjectProcesses { " ^
  "  Get-CimInstance Win32_Process | Where-Object { Test-ProjectProcess $_ } " ^
  "} " ^
  "function Get-ProcessListeners($processIds) { " ^
  "  if (-not $processIds) { return @() } " ^
  "  $idSet=@($processIds); " ^
  "  Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' -and ($idSet -contains $_.OwningProcess) } " ^
  "} " ^
  "$knownPorts=@();" ^
  "$initialTargets=@(Get-ProjectProcesses | Sort-Object ProcessId -Unique);" ^
  "$initialPids=@($initialTargets | Select-Object -ExpandProperty ProcessId);" ^
  "$initialListeners=@(Get-ProcessListeners $initialPids);" ^
  "if ($initialListeners) { " ^
  "  $knownPorts+=@($initialListeners | Select-Object -ExpandProperty LocalPort -Unique); " ^
  "  Write-Host 'Project listening ports:'; " ^
  "  $initialListeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-Table -AutoSize " ^
  "} " ^
  "for ($round=1; $round -le 5; $round++) { " ^
  "  $targets=@(Get-ProjectProcesses | Sort-Object ProcessId -Unique); " ^
  "  if (-not $targets) { if ($round -eq 1) { Write-Host 'No project python processes found.' }; break } " ^
  "  $targetPids=@($targets | Select-Object -ExpandProperty ProcessId); " ^
  "  $listeners=@(Get-ProcessListeners $targetPids); " ^
  "  if ($listeners) { $knownPorts+=@($listeners | Select-Object -ExpandProperty LocalPort -Unique) } " ^
  "  Write-Host ('Cleanup round {0}' -f $round); " ^
  "  foreach ($process in $targets) { " ^
  "    if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) { " ^
  "      Write-Host ('Stopping PID {0}' -f $process.ProcessId); " ^
  "      & taskkill /PID $process.ProcessId /T /F 2>$null | Out-Host " ^
  "    } " ^
  "  } " ^
  "  Start-Sleep -Milliseconds 800 " ^
  "} " ^
  "$remaining=@(Get-ProjectProcesses | Sort-Object ProcessId -Unique); " ^
  "$remainingPids=@($remaining | Select-Object -ExpandProperty ProcessId); " ^
  "$remainingListeners=@(Get-ProcessListeners $remainingPids); " ^
  "if ($remainingListeners) { $knownPorts+=@($remainingListeners | Select-Object -ExpandProperty LocalPort -Unique) } " ^
  "$portsToCheck=@($knownPorts | Sort-Object -Unique); " ^
  "if ($remaining) { " ^
  "  Write-Host 'WARNING: Remaining project processes:'; " ^
  "  $remaining | Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine | Format-List " ^
  "} else { Write-Host 'No remaining project python processes.' } " ^
  "if ($portsToCheck) { " ^
  "  foreach ($port in $portsToCheck) { " ^
  "    $listeners=@(Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }); " ^
  "    if ($listeners) { " ^
  "      Write-Host ('WARNING: Port {0} is still listening:' -f $port); " ^
  "      $listeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-List " ^
  "    } else { Write-Host ('Port {0} is not listening.' -f $port) } " ^
  "  } " ^
  "} else { Write-Host 'No project listening ports found.' }"

set "SHUTDOWN_RESULT=%ERRORLEVEL%"
popd >nul

echo.
echo [Mir2Auto] Shutdown check complete.

if not "%SHUTDOWN_RESULT%"=="0" (
  exit /b %SHUTDOWN_RESULT%
)

endlocal

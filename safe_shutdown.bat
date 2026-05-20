@echo off
setlocal

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo [Mir2Auto] Safe shutdown from:
echo %ROOT%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Resolve-Path -LiteralPath '%ROOT%').Path; " ^
  "$projectScripts = @((Join-Path $root 'py\app.py'), (Join-Path $root 'py\ocr_worker.py'), (Join-Path $root 'app.py'), (Join-Path $root 'ocr_worker.py')); " ^
  "function Test-ProjectCommandLine($commandLine) { " ^
  "  foreach ($path in $projectScripts) { " ^
  "    $slashPath = $path -replace '\\', '/'; " ^
  "    if ($commandLine -like ('*' + $path + '*') -or $commandLine -like ('*' + $slashPath + '*')) { return $true } " ^
  "  } " ^
  "  return $false " ^
  "} " ^
  "function Get-ProjectProcesses { " ^
  "  $portPids = @(Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' } | Select-Object -ExpandProperty OwningProcess -Unique); " ^
  "  Get-CimInstance Win32_Process | Where-Object { " ^
  "    ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -and " ^
  "    ((Test-ProjectCommandLine $_.CommandLine) -or " ^
  "     (($portPids -contains $_.ProcessId) -and ($_.CommandLine -like '*py\app.py*' -or $_.CommandLine -like '*py/app.py*' -or $_.CommandLine -like '*app.py*'))) " ^
  "  } " ^
  "} " ^
  "for ($round = 1; $round -le 5; $round++) { " ^
  "  $targets = @(Get-ProjectProcesses | Sort-Object ProcessId -Unique); " ^
  "  if (-not $targets) { if ($round -eq 1) { Write-Host 'No project python processes found.' }; break } " ^
  "  Write-Host ('Cleanup round {0}' -f $round); " ^
  "  foreach ($process in $targets) { " ^
  "    if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) { " ^
  "      Write-Host ('Stopping PID {0}' -f $process.ProcessId); " ^
  "      & taskkill /PID $process.ProcessId /T /F 2>$null | Out-Host " ^
  "    } " ^
  "  } " ^
  "  Start-Sleep -Milliseconds 800 " ^
  "} " ^
  "$remaining = Get-CimInstance Win32_Process | Where-Object { " ^
  "  ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -and " ^
  "  (Test-ProjectCommandLine $_.CommandLine) " ^
  "}; " ^
  "$listeners = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }; " ^
  "if ($remaining) { " ^
  "  Write-Host 'WARNING: Remaining project processes:'; " ^
  "  $remaining | Select-Object ProcessId, ParentProcessId, CommandLine | Format-List " ^
  "} else { Write-Host 'No remaining project python processes.' } " ^
  "if ($listeners) { " ^
  "  Write-Host 'WARNING: Port 8765 is still listening:'; " ^
  "  $listeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-List " ^
  "} else { Write-Host 'Port 8765 is not listening.' }"

echo.
echo [Mir2Auto] Shutdown check complete.
endlocal

@echo off
setlocal

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "HTTP_PORT=8888"

pushd "%ROOT%" >nul 2>nul
if errorlevel 1 (
  echo Cannot enter project directory: %ROOT%
  pause
  exit /b 1
)

echo [Mir2Auto] Safe shutdown from:
echo %CD%
echo HTTP port: %HTTP_PORT%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root=(Get-Location).Path;" ^
  "$httpPortText='%HTTP_PORT%';" ^
  "if ($httpPortText -notmatch '^\d+$') { Write-Host ('Invalid HTTP_PORT: {0}' -f $httpPortText); exit 1 };" ^
  "$httpPort=[int]$httpPortText;" ^
  "if ($httpPort -lt 1 -or $httpPort -gt 65535) { Write-Host ('Invalid HTTP_PORT: {0}' -f $httpPortText); exit 1 };" ^
  "$projectPython=(Join-Path $root 'runtime\python310\python.exe');" ^
  "$projectPythonSlash=$projectPython -replace '\\','/';" ^
  "$projectScripts=@((Join-Path $root 'py\app.py'));" ^
  "function Test-ProjectPython($process) { " ^
  "  $exePath=$process.ExecutablePath; " ^
  "  if ($exePath -and [string]::Equals($exePath, $projectPython, [StringComparison]::OrdinalIgnoreCase)) { return $true } " ^
  "  $commandLine=$process.CommandLine; " ^
  "  if (-not $commandLine) { return $false } " ^
  "  $slashCommand=$commandLine -replace '\\','/'; " ^
  "  if ($commandLine -like ('*' + $projectPython + '*') -or $slashCommand -like ('*' + $projectPythonSlash + '*')) { return $true } " ^
  "  return $false " ^
  "} " ^
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
  "  if (-not (Test-ProjectPython $process)) { return $false } " ^
  "  return (Test-ProjectCommandLine $process.CommandLine) " ^
  "} " ^
  "function Get-ProjectProcesses { " ^
  "  $portPids=@(Get-NetTCPConnection -LocalPort $httpPort -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' } | Select-Object -ExpandProperty OwningProcess -Unique); " ^
  "  Get-CimInstance Win32_Process | Where-Object { (Test-ProjectProcess $_) -or (($portPids -contains $_.ProcessId) -and (Test-ProjectPython $_)) } " ^
  "} " ^
  "for ($round=1; $round -le 5; $round++) { " ^
  "  $targets=@(Get-ProjectProcesses | Sort-Object ProcessId -Unique); " ^
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
  "$remaining=@(Get-ProjectProcesses | Sort-Object ProcessId -Unique); " ^
  "$listeners=Get-NetTCPConnection -LocalPort $httpPort -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }; " ^
  "if ($remaining) { " ^
  "  Write-Host 'WARNING: Remaining project processes:'; " ^
  "  $remaining | Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine | Format-List " ^
  "} else { Write-Host 'No remaining project python processes.' } " ^
  "if ($listeners) { " ^
  "  Write-Host ('WARNING: Port {0} is still listening:' -f $httpPort); " ^
  "  $listeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-List " ^
  "} else { Write-Host ('Port {0} is not listening.' -f $httpPort) }"

set "SHUTDOWN_RESULT=%ERRORLEVEL%"
popd >nul

echo.
echo [Mir2Auto] Shutdown check complete.

if not "%SHUTDOWN_RESULT%"=="0" (
  exit /b %SHUTDOWN_RESULT%
)

endlocal

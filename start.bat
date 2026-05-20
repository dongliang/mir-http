@echo off
set "BASE_DIR=%~dp0"
set "PYTHON_EXE=%BASE_DIR%runtime\python310\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Missing portable Python runtime: %PYTHON_EXE%
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$base='%BASE_DIR%';" ^
  "$python='%PYTHON_EXE%';" ^
  "$shell=(Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source;" ^
  "if (-not $shell) { $shell='powershell.exe' }" ^
  "$command='& ''' + $python + ''' py\app.py';" ^
  "if (Get-Command wt.exe -ErrorAction SilentlyContinue) {" ^
  "  Start-Process -Verb RunAs -FilePath 'wt.exe' -ArgumentList @('-d', $base, $shell, '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $command)" ^
  "} else {" ^
  "  Start-Process -Verb RunAs -WorkingDirectory $base -FilePath $shell -ArgumentList @('-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $command)" ^
  "}"

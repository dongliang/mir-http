@echo off
set "BASE_DIR=%~dp0"
set "PYTHON_EXE=C:\Users\dongliang\AppData\Local\Programs\Python\Python311-32\python.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$base='%BASE_DIR%';" ^
  "$python='%PYTHON_EXE%';" ^
  "$shell=(Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source;" ^
  "if (-not $shell) { $shell='powershell.exe' }" ^
  "$command='& ''' + $python + ''' app.py';" ^
  "if (Get-Command wt.exe -ErrorAction SilentlyContinue) {" ^
  "  Start-Process -Verb RunAs -FilePath 'wt.exe' -ArgumentList @('-d', $base, $shell, '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $command)" ^
  "} else {" ^
  "  Start-Process -Verb RunAs -WorkingDirectory $base -FilePath $shell -ArgumentList @('-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $command)" ^
  "}"

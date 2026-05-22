@echo off
setlocal

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "HTTP_PORT=8888"
set "PYTHON_EXE=runtime\python310\python.exe"
set "APP_SCRIPT=py\app.py"

pushd "%ROOT%" >nul 2>nul
if errorlevel 1 (
  echo Cannot enter project directory: %ROOT%
  pause
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo Missing portable Python runtime: %CD%\%PYTHON_EXE%
  popd >nul
  pause
  exit /b 1
)

if not exist "%APP_SCRIPT%" (
  echo Missing app script: %CD%\%APP_SCRIPT%
  popd >nul
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root=(Get-Location).Path;" ^
  "$httpPort='%HTTP_PORT%';" ^
  "if ($null -eq $httpPort) { $httpPort='' };" ^
  "$terminal=(Get-Command wt.exe -ErrorAction SilentlyContinue).Source;" ^
  "if (-not $terminal) { Write-Host 'Missing Windows Terminal: wt.exe'; exit 1 };" ^
  "$shell='powershell.exe';" ^
  "if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) { $shell='pwsh.exe' };" ^
  "$rootData=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($root));" ^
  "$portData=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($httpPort));" ^
  "$inner='$env:MIR2AUTO_HTTP_PORT = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String(' + [char]39 + $portData + [char]39 + ')); Set-Location -LiteralPath ([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String(' + [char]39 + $rootData + [char]39 + '))); & ' + [char]39 + '.\runtime\python310\python.exe' + [char]39 + ' ' + [char]39 + '.\py\app.py' + [char]39;" ^
  "$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($inner));" ^
  "Start-Process -Verb RunAs -WorkingDirectory $root -FilePath $terminal -ArgumentList @('-d', $root, $shell, '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded)"

set "START_RESULT=%ERRORLEVEL%"
popd >nul

if not "%START_RESULT%"=="0" (
  pause
  exit /b %START_RESULT%
)

endlocal

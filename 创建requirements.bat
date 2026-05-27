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

(
  echo python-fasthtml
  echo starlette
  echo uvicorn
  echo numpy
  echo Pillow
  echo pywin32
) > requirements.txt

echo Created: %CD%\requirements.txt

popd >nul
endlocal

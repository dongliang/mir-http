@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0runtime\python310\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Missing portable Python runtime: %PYTHON_EXE%
  exit /b 1
)

"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" -m pip install pywin32 python-fasthtml uvicorn paddlepaddle paddleocr
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" -c "import ocr_worker; print('OCR runtime is ready.')"
if errorlevel 1 exit /b 1

echo Portable runtime is ready.

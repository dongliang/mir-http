@echo off
setlocal

cd /d "%~dp0"

py -3.13-64 -m venv .venv-ocr
if errorlevel 1 exit /b 1

".venv-ocr\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

".venv-ocr\Scripts\python.exe" -m pip install paddlepaddle paddleocr
if errorlevel 1 exit /b 1

echo OCR environment is ready.

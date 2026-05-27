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

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$root=(Resolve-Path -LiteralPath '.').Path;" ^
  "$rootPrefix=$root.TrimEnd('\') + '\';" ^
  "$name=Split-Path -Leaf $root;" ^
  "$outDir=Join-Path $root 'dist';" ^
  "New-Item -ItemType Directory -Force -Path $outDir | Out-Null;" ^
  "$stamp=Get-Date -Format 'yyyyMMdd_HHmmss';" ^
  "$zipPath=Join-Path $outDir ($name + '_clean_' + $stamp + '.zip');" ^
  "$excludeDirs=@('.git','.codex','.venv','runtime','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','screenshots','DebugImage','accounts','dist','build');" ^
  "$excludeFiles=@('.sesskey','log.txt','server.out.log','server.err.log','screenshot.bmp');" ^
  "Add-Type -AssemblyName System.IO.Compression;" ^
  "Add-Type -AssemblyName System.IO.Compression.FileSystem;" ^
  "$zip=[System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create);" ^
  "try { Get-ChildItem -LiteralPath $root -Recurse -Force -File | ForEach-Object { $full=$_.FullName; $rel=$full.Substring($rootPrefix.Length).Replace('\','/'); $parts=$rel -split '/'; $skip=$false; foreach ($dir in $excludeDirs) { if ($parts -contains $dir) { $skip=$true; break } }; if (-not $skip -and -not ($excludeFiles -contains $_.Name) -and -not ($_.Extension -in @('.pyc','.pyo','.zip'))) { [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $full, $rel, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null } } } finally { $zip.Dispose() };" ^
  "Write-Host ('Created: ' + $zipPath)"

set "ZIP_RESULT=%ERRORLEVEL%"
popd >nul

if not "%ZIP_RESULT%"=="0" (
  pause
  exit /b %ZIP_RESULT%
)

endlocal

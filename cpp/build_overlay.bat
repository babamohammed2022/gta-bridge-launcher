@echo off
setlocal
set PREMAKE=E:\SDKs\III.VC.SA.LimitAdjuster\premake5.exe
set MSBUILD=C:\Program Files\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\MSBuild.exe
cd /d "%~dp0"
if not exist "%PREMAKE%" (
  echo [FAIL] premake not found at %PREMAKE%
  exit /b 1
)
echo [INFO] premake vs2022 ...
"%PREMAKE%" vs2022
if errorlevel 1 (
  echo [FAIL] premake failed %errorlevel%
  exit /b 1
)
if not exist "build\memory_overlay.sln" (
  echo [FAIL] sln not generated
  dir build
  exit /b 1
)
echo [INFO] msbuild Release Win32 ...
"%MSBUILD%" build\memory_overlay.sln /p:Configuration=Release /p:Platform=Win32 /m /nologo
if errorlevel 1 (
  echo [FAIL] msbuild failed %errorlevel%
  exit /b 1
)
if exist "bin\memory_overlay.asi" (
  echo [OK] bin\memory_overlay.asi built
  dir bin\memory_overlay.asi
) else (
  echo [FAIL] asi not found after build
  dir bin 2>nul
  dir build 2>nul
  exit /b 1
)
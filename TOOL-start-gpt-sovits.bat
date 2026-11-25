@echo off
setlocal
chcp 65001 >nul
title BandoriPet - GPT-SoVITS v2
set "SOVITS_DIR=%~1"
if not defined SOVITS_DIR set "SOVITS_DIR=%BANDORI_GPT_SOVITS_DIR%"
if not defined SOVITS_DIR if exist "D:\BANDORI-GPT-SoVITS\GPT-SoVITS-v2-240821" set "SOVITS_DIR=D:\BANDORI-GPT-SoVITS\GPT-SoVITS-v2-240821"
if not defined SOVITS_DIR set "SOVITS_DIR=D:\BANDORI-GPT-SoVITS\runtime-v2"
set "LOCAL_CONFIG=%~dp0server\tts_infer_local.yaml"
set "RUNTIME_CONFIG=%SOVITS_DIR%\GPT_SoVITS\configs\bandoripet_local.yaml"

if not exist "%SOVITS_DIR%\api_v2.py" goto :missing
if not exist "%SOVITS_DIR%\runtime\python.exe" goto :missing
if not exist "%LOCAL_CONFIG%" goto :missing
pushd "%SOVITS_DIR%" || exit /b 1
copy /y "%LOCAL_CONFIG%" "%RUNTIME_CONFIG%" >nul
if errorlevel 1 (
    popd
    exit /b 1
)
set "PATH=%SOVITS_DIR%;%SOVITS_DIR%\runtime;%SOVITS_DIR%\runtime\Scripts;%PATH%"

echo [*] GPT-SoVITS v2 at http://127.0.0.1:9880/
echo [*] CUDA and FP16 are configured in bandoripet_local.yaml.
"%SOVITS_DIR%\runtime\python.exe" api_v2.py -a 127.0.0.1 -p 9880 -c "%RUNTIME_CONFIG%"
set "STATUS=%ERRORLEVEL%"
popd
if not "%STATUS%"=="0" pause
exit /b %STATUS%

:missing
echo [!] GPT-SoVITS v2 runtime or local YAML not found.
echo Runtime: "%SOVITS_DIR%"
echo Local YAML: "%LOCAL_CONFIG%"
echo Pass the extracted package directory as the first argument if needed.
pause
exit /b 1

@echo off
setlocal

:: This script manages the local installation of the rescile-ce binary for Windows.
:: It detects the architecture, downloads the latest release, verifies its checksum,
:: and adds it to the current Command Prompt session's PATH.
::
:: Usage: init.bat
::
:: Dependencies: curl.exe and powershell.exe (both included in modern Windows)

:: --- Configuration ---
set "SCRIPT_DIR=%~dp0"
set "BIN_DIR=%SCRIPT_DIR%..\.bin"
set "BINARY_NAME=rescile-ce.exe"
set "BINARY_PATH=%BIN_DIR%\%BINARY_NAME%"
set "INDEX_URL=https://updates.rescile.com/index.json"
set "ASSET_KEY=windows-amd64"

:: --- Main Logic ---
if exist "%BINARY_PATH%" (
    echo [INFO] rescile-ce is already installed at %BINARY_PATH%
) else (
    echo [INFO] rescile-ce not found. Starting installation...

    :: Check for dependencies
    where /q curl || (echo [ERROR] curl.exe not found in PATH. & exit /b 1)
    where /q powershell || (echo [ERROR] powershell.exe not found in PATH. & exit /b 1)

    :: Platform detection
    if /i not "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
        echo [ERROR] Unsupported architecture: %PROCESSOR_ARCHITECTURE%. Only AMD64 is supported.
        exit /b 1
    )
    echo [INFO] Platform detected: %ASSET_KEY%

    :: Fetch download info using a PowerShell one-liner for reliability
    echo [INFO] Fetching latest version info from %INDEX_URL%...
        for /f "tokens=*" %%i in ('powershell -NoProfile -Command "$ErrorActionPreference='Stop'; try { $json = Invoke-WebRequest -Uri '%INDEX_URL%' -UseBasicParsing | ConvertFrom-Json; $item = $json.release.'%ASSET_KEY%'; if (-not $item) { $item = $json.pre.'%ASSET_KEY%' }; if (-not $item) { exit 1 }; Write-Output \"$($item.url)|$($item.sha256)\" } catch { exit 1 }"') do (
        set "DOWNLOAD_INFO=%%i"
    )

    if not defined DOWNLOAD_INFO (
        echo [ERROR] Failed to fetch download URL and checksum.
        exit /b 1
    )

    for /f "tokens=1,2 delims=|" %%a in ("%DOWNLOAD_INFO%") do (
        set "DOWNLOAD_URL=%%a"
        set "EXPECTED_SHA=%%b"
    )

    if not defined DOWNLOAD_URL (echo [ERROR] Could not parse download URL. & exit /b 1)
    if not defined EXPECTED_SHA (echo [ERROR] Could not parse checksum. & exit /b 1)

    :: Download
    if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
    set "TMP_FILE=%BINARY_PATH%.tmp.%RANDOM%"
    echo [INFO] Downloading from %DOWNLOAD_URL%...
    curl --progress-bar --fail --location "%DOWNLOAD_URL%" --output "%TMP_FILE%"
    if errorlevel 1 (
        echo [ERROR] Download failed.
        if exist "%TMP_FILE%" del "%TMP_FILE%"
        exit /b 1
    )

    :: Verify checksum using PowerShell for reliability
    echo [INFO] Verifying checksum...
    for /f "usebackq" %%H in (`powershell -NoProfile -Command "(Get-FileHash -Path '%TMP_FILE%' -Algorithm SHA256).Hash.ToLower()"`) do (
        set "CALCULATED_SHA=%%H"
    )

    if /i not "%CALCULATED_SHA%"=="%EXPECTED_SHA%" (
        echo [ERROR] Checksum verification failed!
        echo   Expected: %EXPECTED_SHA%
        echo   Got:      %CALCULATED_SHA%
        if exist "%TMP_FILE%" del "%TMP_FILE%"
        exit /b 1
    )
    echo [INFO] Checksum verified.

    :: Install
    move "%TMP_FILE%" "%BINARY_PATH%" >nul
    echo [SUCCESS] Installed rescile-ce to %BINARY_PATH%
)

:: --- Final Step: Add to session PATH ---
:: The 'endlocal & set "PATH=%PATH%"' trick persists the PATH change
:: after the script's local environment is discarded.
endlocal & set "PATH=%BIN_DIR%;%PATH%"
echo [INFO] Added "%BIN_DIR%" to the current session's PATH.

#
# This script manages the local installation of the rescile-ce binary for Windows.
# It detects the architecture, downloads the latest release, verifies its checksum,
# and adds it to the current PowerShell session's PATH.
#
# Usage (from a PowerShell terminal):
# 1. PS> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
# 2. PS> .\init.ps1
#
# Dependencies: PowerShell 5.1+

# --- Configuration ---
$ErrorActionPreference = 'Stop'
$BinDir = Join-Path $PSScriptRoot "..\.bin"
$BinaryName = "rescile-ce.exe"
$BinaryPath = Join-Path $BinDir $BinaryName
$IndexUrl = "https://updates.rescile.com/index.json"

# --- Main Logic ---
try {
    # Check if already installed
    if (Test-Path -Path $BinaryPath -PathType Leaf) {
        Write-Host "[INFO] rescile-ce is already installed at $BinaryPath" -ForegroundColor Blue
    } else {
        Write-Host "[INFO] rescile-ce not found. Starting installation..." -ForegroundColor Blue

        # Platform detection
        if ($env:PROCESSOR_ARCHITECTURE -ne "AMD64") {
            throw "Unsupported architecture: $($env:PROCESSOR_ARCHITECTURE). Only AMD64 is supported."
        }
        $assetKey = "windows-amd64"
        Write-Host "[INFO] Platform detected: $assetKey" -ForegroundColor Blue

        # Fetch update index
        Write-Host "[INFO] Fetching latest version from $IndexUrl" -ForegroundColor Blue
        $indexContent = Invoke-WebRequest -Uri $IndexUrl -UseBasicParsing
        $index = $indexContent.Content | ConvertFrom-Json

        $assetInfo = $index.release.$assetKey
        if (-not $assetInfo) {
            Write-Host "[INFO] No asset in 'release' channel. Checking 'pre' channel..." -ForegroundColor Blue
            $assetInfo = $index.pre.$assetKey
        }
        if (-not $assetInfo) {
            throw "Could not find asset for platform '$assetKey' in 'release' or 'pre' channels."
        }
        $downloadUrl = $assetInfo.url
        $expectedSha = $assetInfo.sha256

        # Download binary
        if (-not (Test-Path -Path $BinDir -PathType Container)) {
            New-Item -Path $BinDir -ItemType Directory -Force | Out-Null
        }
        $tmpFile = Join-Path $BinDir "$($BinaryName).tmp.$($PID)"
        Write-Host "[INFO] Downloading from $downloadUrl..." -ForegroundColor Blue
        Invoke-WebRequest -Uri $downloadUrl -OutFile $tmpFile

        # Verify checksum
        Write-Host "[INFO] Verifying checksum..." -ForegroundColor Blue
        $calculatedHash = (Get-FileHash -Path $tmpFile -Algorithm SHA256).Hash.ToLower()
        if ($calculatedHash -ne $expectedSha) {
            Remove-Item $tmpFile -ErrorAction SilentlyContinue
            throw "Checksum verification failed! Expected: $expectedSha, Got: $calculatedHash"
        }
        Write-Host "[INFO] Checksum verified." -ForegroundColor Blue

        # Install
        Move-Item -Path $tmpFile -Destination $BinaryPath -Force
        Write-Host "[SUCCESS] Installed rescile-ce to $BinaryPath" -ForegroundColor Green
    }

    # --- Final Step: Add to session PATH ---
    $absBinDir = (Resolve-Path $BinDir).Path
    if ($env:Path -notlike "*$absBinDir*") {
        $env:Path = "$absBinDir;$($env:Path)"
        Write-Host "[INFO] Added '$absBinDir' to the current session's PATH." -ForegroundColor Yellow
    }

} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

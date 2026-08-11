#!/usr/bin/env bash
#
# This script manages the local installation of the rescile-ce binary.
# It detects the OS and architecture, downloads the latest release, verifies its
# checksum, and outputs the command to add it to the current shell's PATH.
#
# Usage: eval "$(./init.sh)"
#
# Dependencies: curl, jq

# Exit immediately if a command exits with a non-zero status.
set -e
# Treat unset variables as an error.
set -u
# Pipes fail on the first non-zero status in the pipe.
set -o pipefail

# --- Configuration ---
INDEX_URL="https://updates.rescile.com/index.json"
# Get the directory where the script is located to define BIN_DIR relative to it.
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
BIN_DIR="${SCRIPT_DIR}/../.bin"
BINARY_NAME="rescile-ce"
BINARY_PATH="${BIN_DIR}/${BINARY_NAME}"

# --- Helper Functions ---
# Use tput for colors if available, otherwise use plain text.
if tput setaf 1 >/dev/null 2>&1; then
    BLUE=$(tput setaf 4)
    GREEN=$(tput setaf 2)
    RED=$(tput setaf 1)
    RESET=$(tput sgr0)
else
    BLUE=""
    GREEN=""
    RED=""
    RESET=""
fi

log_status() {
    echo "${BLUE}[INFO]${RESET} $1" >&2
}

log_success() {
    echo "${GREEN}[SUCCESS]${RESET} $1" >&2
}

log_error() {
    echo "${RED}[ERROR]${RESET} $1" >&2
}

get_asset_key() {
  local os arch
  os=$(uname -s | tr '[:upper:]' '[:lower:]')
  arch=$(uname -m)

  case "${os}-${arch}" in
    linux-x86_64)   echo "linux-amd64" ;;
    darwin-aarch64) echo "darwin-arm64" ;;
    darwin-arm64)   echo "darwin-arm64" ;;
    *)
      log_error "Unsupported platform for automated download: ${os}-${arch}"
      return 1
      ;;
  esac
}

verify_checksum() {
  local file_path="$1"
  local expected_checksum="$2"
  local calculated_checksum

  if command -v sha256sum >/dev/null; then
    calculated_checksum=$(sha256sum "${file_path}" | awk '{print $1}')
  elif command -v shasum >/dev/null; then
    calculated_checksum=$(shasum -a 256 "${file_path}" | awk '{print $1}')
  else
    log_error "Could not find 'sha256sum' or 'shasum' to verify download."
    return 1
  fi

  if [[ "${calculated_checksum}" != "${expected_checksum}" ]]; then
    log_error "Checksum verification failed!"
    log_error "  Expected: ${expected_checksum}"
    log_error "  Got:      ${calculated_checksum}"
    return 1
  fi
}

# --- Main Logic ---
main() {
    if [[ -x "${BINARY_PATH}" ]]; then
        log_status "rescile-ce is already installed at ${BINARY_PATH}"
    else
        log_status "rescile-ce not found. Attempting to download the latest version."

        command -v curl >/dev/null || { log_error "'curl' is required but not found in PATH."; exit 1; }
        command -v jq >/dev/null   || { log_error "'jq' is required but not found in PATH."; exit 1; }

        local asset_key
        asset_key=$(get_asset_key) || exit 1
        log_status "Platform detected: ${asset_key}"

        log_status "Fetching latest version from ${INDEX_URL}"
        local index_content
        index_content=$(curl --silent --fail --location "${INDEX_URL}")

        local update_channel="release"
        local asset_info
        asset_info=$(echo "${index_content}" | jq --arg tag "${update_channel}" --arg key "${asset_key}" '.[$tag][$key]')

        if [[ $(echo "${asset_info}" | jq -r '.url') == "null" ]]; then
            log_status "No asset found in '${update_channel}' channel. Checking 'pre' channel..."
            update_channel="pre"
            asset_info=$(echo "${index_content}" | jq --arg tag "${update_channel}" --arg key "${asset_key}" '.[$tag][$key]')
        fi

        local download_url
        download_url=$(echo "${asset_info}" | jq -r '.url')
        local expected_sha
        expected_sha=$(echo "${asset_info}" | jq -r '.sha256')

        if [[ "${download_url}" == "null" || "${expected_sha}" == "null" ]]; then
            log_error "Could not find asset for channel 'release' or 'pre' on platform '${asset_key}'."
            exit 1
        fi

        mkdir -p "${BIN_DIR}"
        local tmp_file="${BINARY_PATH}.tmp.$$"

        log_status "Downloading from ${download_url}..."
        if ! curl --progress-bar --fail --location "${download_url}" --output "${tmp_file}"; then
            log_error "Download failed."
            rm -f "${tmp_file}"
            exit 1
        fi

        log_status "Verifying checksum..."
        if ! verify_checksum "${tmp_file}" "${expected_sha}"; then
            rm -f "${tmp_file}"
            exit 1
        fi
        log_status "Checksum verified."

        chmod +x "${tmp_file}"
        mv "${tmp_file}" "${BINARY_PATH}"

        log_success "Installed rescile-ce to ${BINARY_PATH}"
    fi

    # --- Final Step: Output PATH command to stdout ---
    # This is the only output to stdout, intended for `eval`.
    echo "export PATH=\"${BIN_DIR}:\$PATH\""
}

main

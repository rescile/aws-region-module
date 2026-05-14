#!/usr/bin/env bash
set -eo pipefail

# Configuration
API_URL=${RESCILE_API_URL:-"http://localhost:7600"}
OUTPUT_DIR=${SYNC_OUTPUT_DIR:-"module"}
ARCHIVE_DIR="$(dirname "$OUTPUT_DIR")/archive"

# Colors and formatting
BLUE='\033[34m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
BOLD='\033[1m'
RESET='\033[0m'

echo -e "${BOLD}${BLUE}=======================================${RESET}"
echo -e "${BOLD}${BLUE}       Rescile Sync Script             ${RESET}"
echo -e "${BOLD}${BLUE}=======================================${RESET}\n"

# Ensure dependencies
if ! command -v jq &> /dev/null; then
    echo -e "${RED}Error: 'jq' is not installed. Please install jq to continue.${RESET}"
    exit 1
fi
if ! command -v curl &> /dev/null; then
    echo -e "${RED}Error: 'curl' is not installed. Please install curl to continue.${RESET}"
    exit 1
fi

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

EXPECTED_FILES="$TMP_DIR/expected.txt"
touch "$EXPECTED_FILES"

# 2. Fetch outputs index
echo -e "${YELLOW}>> Fetching output index...${RESET}"
if ! OUTPUTS=$(curl -s "$API_URL/api/outputs/index"); then
    echo -e "${RED}Error: Failed to fetch outputs index from $API_URL${RESET}"
    exit 1
fi

if ! echo "$OUTPUTS" | jq -e 'type == "array"' > /dev/null 2>&1; then
    echo -e "${RED}Error: Invalid outputs index format.${RESET}"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

CHANGED=0
MISSING=0
UNCHANGED=0

echo -e "${YELLOW}>> Syncing files to '$OUTPUT_DIR/'...${RESET}"

while IFS=$'\t' read -r o_type o_name o_filename o_hash o_url origin_name; do
    if [[ -z "$o_filename" || "$o_filename" == "null" ]]; then
        o_filename="$o_name"
    fi

    if [[ -z "$origin_name" || "$origin_name" == "null" ]]; then
        origin_name="global"
    fi

    TARGET_DIR="$OUTPUT_DIR"
    TARGET_FILE="$TARGET_DIR/$o_filename"
    echo "$TARGET_FILE" >> "$EXPECTED_FILES"

    mkdir -p "$TARGET_DIR"

    NEEDS_DOWNLOAD=false
    STATUS=""

    if [[ ! -f "$TARGET_FILE" ]]; then
        NEEDS_DOWNLOAD=true
        STATUS="${BOLD}${GREEN}Missing${RESET} (downloading)"
        MISSING=$((MISSING + 1))
    else
        # check hash
        if command -v sha256sum >/dev/null 2>&1; then
            LOCAL_HASH=$(sha256sum "$TARGET_FILE" | awk '{print $1}')
        else
            LOCAL_HASH=$(shasum -a 256 "$TARGET_FILE" | awk '{print $1}')
        fi

        EXPECTED_SHA=${o_hash#sha256-}

        if [[ "$LOCAL_HASH" != "$EXPECTED_SHA" ]]; then
            NEEDS_DOWNLOAD=true
            STATUS="${BOLD}${YELLOW}Changed${RESET} (updating)   "
            CHANGED=$((CHANGED + 1))
        else
            STATUS="${GREEN}Unchanged${RESET}            "
            UNCHANGED=$((UNCHANGED + 1))
        fi
    fi

    if $NEEDS_DOWNLOAD; then
        echo -e "  [ $STATUS ] $OUTPUT_DIR/$origin_name/$o_filename"
        if [[ -f "$TARGET_FILE" ]]; then
            TMP_DL="$TMP_DIR/tmp_dl"
            curl -s "$API_URL$o_url" -o "$TMP_DL"
            # diff -u "$TARGET_FILE" "$TMP_DL" || true
            mv "$TMP_DL" "$TARGET_FILE"
        else
            curl -s "$API_URL$o_url" -o "$TARGET_FILE"
        fi
        if [[ "$TARGET_FILE" == *.sh ]]; then
            chmod +x "$TARGET_FILE"
        fi
    fi

done < <(echo "$OUTPUTS" | jq -r '.[] | "\(.type)\t\(.name)\t\(.filename)\t\(.hash)\t\(.download_url)\t\(.origin.name)"')

# 3. Check for removed files
REMOVED=0
echo -e "${YELLOW}>> Checking for obsolete files...${RESET}"
while read -r existing_file; do
    if [[ -n "$existing_file" ]] && ! grep -Fxq "$existing_file" "$EXPECTED_FILES"; then
        rel_path="${existing_file#$OUTPUT_DIR/}"
        mkdir -p "$(dirname "$ARCHIVE_DIR/$rel_path")"
        mv "$existing_file" "$ARCHIVE_DIR/$rel_path"
        echo -e "  [ ${BOLD}${RED}Archived${RESET} ] $ARCHIVE_DIR/${rel_path}"
        REMOVED=$((REMOVED + 1))
    fi
done < <(find "$OUTPUT_DIR" -type f 2>/dev/null || true)

# Clean up empty directories
find "$OUTPUT_DIR" -type d -empty -delete 2>/dev/null || true

echo -e "\n${BOLD}${BLUE}====== Sync Summary ======${RESET}"
echo -e "  Downloaded: ${BOLD}${GREEN}$MISSING${RESET}"
echo -e "  Updated:    ${BOLD}${YELLOW}$CHANGED${RESET}"
echo -e "  Archived:   ${BOLD}${RED}$REMOVED${RESET}"
echo -e "  Unchanged:  ${BOLD}$UNCHANGED${RESET}"
echo -e "${BOLD}${BLUE}==========================${RESET}\n"

#!/usr/bin/env bash

IANA_URL="https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.csv"
TEMP_CSV="iana_registry.tmp"
OUTPUT_FILE="input/iana_registry.json"

mkdir -p "$(dirname "$OUTPUT_FILE")"

echo "Fetching live RFC port data..."
# curl -L follows redirects; tr -d '\r' removes Windows line endings
curl -sL "$IANA_URL" | tr -d '\r' > "$TEMP_CSV"

echo "Processing JSON..."

# Start JSON array
echo "[" > "$OUTPUT_FILE"

# Pre-process the CSV with sed to replace commas inside quotes with a placeholder
# then use awk to parse. This is more ubiquitous than gawk's FPAT.
sed -E 's/"([^",]+),([^"]+)"/"\1 \2"/g' "$TEMP_CSV" | \
awk -F',' '
NR > 1 {
    # Strip any remaining quotes
    gsub(/"/, "", $1); gsub(/"/, "", $2); gsub(/"/, "", $3); gsub(/"/, "", $4);

    port = $2;

    # Check if port is a numeric System Port or one of our User Port selections[cite: 1]
    if (port ~ /^[0-9]+$/) {
        if ((port > 0 && port <= 1023) || port ~ /^(1433|3000|3306|5432|6379|8080|27017)$/) {

            # Escape JSON-breaking characters in description[cite: 1]
            gsub(/\\/, "\\\\", $4);

            printf "  {\n    \"service\": \"%s\",\n    \"port\": %d,\n    \"protocol\": \"%s\",\n    \"description\": \"%s\"\n  },\n", $1, port, $3, $4
        }
    }
}' >> "$OUTPUT_FILE"

# Remove trailing comma and close JSON[cite: 1]
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' '$ s/,$//' "$OUTPUT_FILE"
else
    sed -i '$ s/,$//' "$OUTPUT_FILE"
fi

echo "]" >> "$OUTPUT_FILE"

rm "$TEMP_CSV"
echo "Done! Generated $OUTPUT_FILE"

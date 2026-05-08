#!/usr/bin/env bash

IANA_URL="https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.csv"
TEMP_CSV="iana_registry.tmp"
OUTPUT_FILE="input/iana_port_registry.json"

mkdir -p "$(dirname "$OUTPUT_FILE")"

echo "Fetching live RFC port data..."
curl -sL "$IANA_URL" | tr -d '\r' > "$TEMP_CSV"

echo "Processing JSON Map..."

# 1. Start the JSON object (using > to overwrite any old data)
echo "{" > "$OUTPUT_FILE"

# 2. Process CSV into Map format
sed -E 's/"([^",]+),([^"]+)"/"\1 \2"/g' "$TEMP_CSV" | \
awk -F',' '
NR > 1 {
    gsub(/"/, "", $1); gsub(/"/, "", $2); gsub(/"/, "", $3); gsub(/"/, "", $4);

    port = $2;

    if (port ~ /^[0-9]+$/) {
        if ((port > 0 && port <= 1023) || port ~ /^(1433|3000|3306|5432|6379|8080|27017)$/) {

            gsub(/\\/, "\\\\", $4);
            gsub(/"/, "\\\"", $4);

            # This creates the "key": { ... } structure
            key = port "/" $3;

            printf "  \"%s\": {\n    \"service\": \"%s\",\n    \"port\": %d,\n    \"protocol\": \"%s\",\n    \"description\": \"%s\"\n  },\n", key, $1, port, $3, $4
        }
    }
}' >> "$OUTPUT_FILE"

# 3. Finalize JSON: Remove trailing comma and close
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' '$ s/,$//' "$OUTPUT_FILE"
else
    sed -i '$ s/,$//' "$OUTPUT_FILE"
fi

echo "}" >> "$OUTPUT_FILE"

rm "$TEMP_CSV"
echo "Done! Generated Map in $OUTPUT_FILE"

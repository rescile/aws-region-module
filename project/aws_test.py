import os

import boto3

print(f"DEBUG: Config File Env: {os.environ.get('AWS_CONFIG_FILE')}")
print(f"DEBUG: Active Region: {boto3.Session().region_name}")

# Falls die Datei im Standardpfad (~/.aws/credentials) liegt,
# reicht dieser einfache Aufruf:
session = boto3.Session()

# Teste die Verbindung (z.B. Identität abfragen)
sts = session.client("sts")
try:
    identity = sts.get_caller_identity()
    print(f"Erfolg! Eingeloggt als User-ID: {identity['UserId']}")
except Exception as e:
    print(f"Fehler beim Login: {e}")

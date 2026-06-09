import os
import sys

from simple_salesforce.api import Salesforce

INSTANCE_URL = os.environ.get("SF_INSTANCE_URL")
ACCESS_TOKEN = os.environ.get("SF_ACCESS_TOKEN")

if not INSTANCE_URL or not ACCESS_TOKEN:
    print(
        "❌ Error: Environment variables 'SF_INSTANCE_URL' and 'SF_ACCESS_TOKEN' must be set.",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    sf = Salesforce(
        instance_url=INSTANCE_URL,
        session_id=ACCESS_TOKEN,
        username="",
        version="61.0",  # Private Connect metadata fields require modern API versions
    )
    print(f"--> Securely authenticated to Salesforce instance: {INSTANCE_URL}")

    # --- Define Private Connect Payload ---
    connection_payload = {
        "FullName": "AWS_VPC_Inbound_Link",  # Unique API name
        "Metadata": {
            "label": "Production AWS VPC Inbound Link",
            "description": "Managed inbound link via automated infrastructure orchestrator.",
            "connectionType": "AwsPrivateLink",  # Salesforce architecture pairing type
            # The service name exposed by your AWS VPC Endpoint Service configuration
            "awsServiceId": "com.amazonaws.vpce.eu-central-2.vpce-svc-0123456789abcdef0",
            "status": "Unprovisioned",  # Initial state prior to activation handshake
        },
    }

    print("Initiating Private Connect provision pass via Tooling API...")

    # --- Execute the Provisioning Request ---
    result = sf.toolingexecute(
        "sobjects/InboundNetworkConnection", method="POST", json=connection_payload
    )

    # --- Output Orchestration Results ---
    print("Private Connect object successfully staged in Salesforce!")
    print(f"--> Connection Record ID: {result.get('id')}")
    print(f"--> Success Status: {result.get('success')}")
    print(
        "\n Next Step: Log into Setup -> Private Connect to authorize the sync handshake or use the record ID to monitor readiness state via script."
    )

except Exception as e:
    print(f"Operation failed: {e}", file=sys.stderr)
    sys.exit(1)

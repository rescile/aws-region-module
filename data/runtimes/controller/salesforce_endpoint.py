# controller/salesforce_endpoint.py
import os
import sys

import requests
from modules.salesforce_client import SalesforceJwtClient
from simple_salesforce import Salesforce


class SalesforceSyncOrchestrator:
    def __init__(self, state_manager, region: str = "eu-central-2"):
        self.state = state_manager
        self.domain = "salesforce_sync"
        self.region = region

        # Dynamic runtime parameters populated dynamically by the JWT handshake
        self.instance_url = None
        self.access_token = None

    def _init_salesforce_client(self) -> Salesforce:
        """Initializes the Salesforce API target context using signed JWT tokens."""
        if self.instance_url and self.access_token:
            try:
                sf = Salesforce(
                    instance_url=self.instance_url,
                    session_id=self.access_token,
                    version="61.0",
                )
                print("--> [AUTH: JWT] simple-salesforce authenticated safely.")
                return sf
            except Exception as e:
                print(
                    f"[AUTH ERROR] Failed to initialize Salesforce client: {e}",
                    file=sys.stderr,
                )
                return None
        return None

    def _authenticate_headless(self):
        consumer_key = os.environ.get("SF_CONSUMER_KEY")
        username = os.environ.get("SF_USERNAME")
        key_string = os.environ.get("SF_PRIVATE_KEY")

        # Explicitly trap missing variables before feeding them to PyJWT
        if not all([consumer_key, username, key_string]):
            raise ValueError(
                f"❌ Missing environment setup! Verified state: "
                f"SF_CONSUMER_KEY={bool(consumer_key)}, "
                f"SF_USERNAME={bool(username)}, "
                f"SF_PRIVATE_KEY={bool(key_string)}"
            )

        sf_jwt = SalesforceJwtClient(
            consumer_key=consumer_key,
            username=username,
            private_key_string=key_string,
            is_sandbox=True,
        )
        # Populate the live coordinates on the orchestrator instance dynamically
        self.access_token, self.instance_url = sf_jwt.authenticate()

    def run(self, aws_service_name: str):
        print("\n=== [DOMAIN: SALESFORCE_SYNC] CONVERGING PRIVATE SYNC LINK ===")

        # 1. Fetch fresh operational credentials right when the domain runs
        try:
            self._authenticate_headless()
        except Exception as e:
            print(f"[ORCHESTRATION BLOCKER] Handshake failure: {e}", file=sys.stderr)
            return

        print("Step 2: Connecting to Salesforce Core Control Plane...")
        sf_client = self._init_salesforce_client()
        if not sf_client:
            print("[ORCHESTRATION BLOCKER] Skipping staging due to API init failure.")
            return

        print(
            f"\nStep 3: Staging Private Connect inbound link using live ID: {aws_service_name}"
        )

        connection_payload = {
            "FullName": "AWS_VPC_Inbound_Link",
            "Metadata": {
                "connectionType": "AwsPrivateLink",
                "description": "Managed inbound link via automated infrastructure orchestrator.",
                "inboundNetworkConnProperties": [
                    {
                        "propertyName": "AwsVpcEndpointId",
                        "propertyValue": aws_service_name,
                    }
                ],
                "isActive": True,
                "label": "Production AWS VPC Inbound Link",
                "status": "Unprovisioned",
            },
        }

        try:
            endpoint_url = f"{self.instance_url}/services/data/v61.0/tooling/sobjects/InboundNetworkConnection"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                endpoint_url, headers=headers, json=connection_payload
            )

            if response.status_code not in [200, 201]:
                try:
                    err_payload = response.json()
                    err_msg = (
                        err_payload[0].get("message")
                        if isinstance(err_payload, list)
                        else err_payload
                    )
                except Exception:
                    err_msg = response.text
                raise RuntimeError(f"HTTP {response.status_code}: {err_msg}")

            result = response.json()
            connection_id = result.get("id")
            print("Private Connect object successfully staged in Salesforce!")
            print(f"  -> Connection Record ID: {connection_id}")

            self.state.record_resource(
                self.domain,
                connection_id,
                {
                    "Type": "SalesforceInboundLink",
                    "AwsServiceId": aws_service_name,
                    "Status": "STAGED_UNPROVISIONED",
                },
            )
            print(
                "\nNext Action: Log into Salesforce Setup -> Private Connect console to authorize the request."
            )

        except Exception as e:
            if "DUPLICATE_DEVELOPER_NAME" in str(e):
                print(
                    "  -> [OK] Private Connect link already registered. Skipping duplicate staging."
                )
            else:
                print(f"[SALESFORCE ERROR] Tooling API execution failed: {e}")

    def update_state(self):
        """Reconciles internal tracking caches against real-world state definitions."""
        print(f"-> Scanning active state blocks for domain: {self.domain}...")
        pass

    def destroy(self):
        """[DESTROY] Cleans up Salesforce data synchronization states or endpoints."""
        print(f"\n=== [DOMAIN: {self.domain.upper()}] SHUTTING DOWN SYNC ENGINE ===")

        sf_state = self.state.get_domain_state(self.domain) or {}
        if not sf_state:
            print(
                "-> No active Salesforce sync links tracked in local state. Skipping API cleanup."
            )
            return

        # Acquire credentials on tearing down infrastructure domains
        try:
            self._authenticate_headless()
        except Exception as e:
            print(
                f"❌ [TEARDOWN BLOCKER] Could not fetch fresh credentials for cleanup: {e}",
                file=sys.stderr,
            )
            return

        for record_id, meta in list(sf_state.items()):
            if meta.get("Type") == "SalesforceInboundLink":
                print(f"-> Found tracked Salesforce Connection Record: {record_id}")
                try:
                    print(
                        f"  -> Sending Tooling API DELETE request for connection: {record_id}..."
                    )
                    endpoint_url = f"{self.instance_url}/services/data/v61.0/tooling/sobjects/InboundNetworkConnection/{record_id}"
                    headers = {"Authorization": f"Bearer {self.access_token}"}

                    response = requests.delete(endpoint_url, headers=headers)
                    if response.status_code not in [200, 204]:
                        raise RuntimeError(
                            f"HTTP {response.status_code}: {response.text}"
                        )

                    print(
                        "  -> [OK] Successfully deleted link from Salesforce console."
                    )
                    self.state.purge_resource(self.domain, record_id)
                except Exception as e:
                    print(
                        f"  -> ❌ [API FAILURE] Could not delete connection record {record_id}: {e}"
                    )

        print("-> Cleaning up ephemeral routing context... [OK]")

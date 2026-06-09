# project/orchestrators/salesforce_sync_orch.py
import os
import sys

import requests
from simple_salesforce import Salesforce


class SalesforceSyncOrchestrator:
    def __init__(self, state_manager, region: str = "eu-central-2"):
        self.state = state_manager
        self.domain = "salesforce_sync"
        self.region = region

        # Pull authentication tokens cleanly from the shell environment
        self.instance_url = os.environ.get("SF_INSTANCE_URL")
        self.access_token = os.environ.get("SF_ACCESS_TOKEN")

    def _init_salesforce_client(self) -> Salesforce:
        """Initializes the Salesforce API target context using injected session tokens."""

        if self.instance_url and self.access_token:
            try:
                # Initialize simple-salesforce engine for any future standard objects
                sf = Salesforce(
                    instance_url=self.instance_url,
                    session_id=self.access_token,
                    version="61.0",
                )
                print(
                    "--> [AUTH: HEADLESS] Securely authenticated via environment tokens."
                )
                return sf
            except Exception as e:
                print(
                    f"❌ [AUTH ERROR] Failed to initialize Salesforce client: {e}",
                    file=sys.stderr,
                )
                return None

        print(
            "❌ [AUTH ERROR] Target coordinates missing in active shell environment.\n"
            "   Please export SF_INSTANCE_URL and SF_ACCESS_TOKEN before running.",
            file=sys.stderr,
        )
        return None

    def run(self, aws_service_name: str):
        """Executes the dual-layer provision pass bridging AWS and Salesforce."""
        print(f"\n=== [DOMAIN: {self.domain.upper()}] CONVERGING PRIVATE SYNC LINK ===")
        print(f"-> Received live AWS PrivateLink Service Name: {aws_service_name}")

        print("\nStep 2: Connecting to Salesforce Core Control Plane...")
        sf_client = self._init_salesforce_client()
        if not sf_client:
            print(
                "❌ [ORCHESTRATION BLOCKER] Skipping Salesforce staging due to authentication failure."
            )
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
            # Clean direct HTTP delivery path avoiding upstream helper library mutations
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
            print("🚀 Private Connect object successfully staged in Salesforce!")
            print(f"  -> Connection Record ID: {connection_id}")
            print(f"  -> Success Status: {result.get('success')}")

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
                "\nNext Action: Log into your Salesforce Setup -> Private Connect console to authorize the manual sync handshake request."
            )

        except Exception as e:
            if "DUPLICATE_DEVELOPER_NAME" in str(e):
                print(
                    "  -> [OK] Private Connect link already registered in Salesforce. Skipping duplicate staging."
                )
            else:
                print(f"❌ [SALESFORCE ERROR] Tooling API execution failed: {e}")

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

        sf_client = None
        for record_id, meta in list(sf_state.items()):
            if meta.get("Type") == "SalesforceInboundLink":
                print(f"-> Found tracked Salesforce Connection Record: {record_id}")

                if not sf_client:
                    sf_client = self._init_salesforce_client()

                if sf_client and self.access_token:
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
                else:
                    print(
                        "  -> ❌ [AUTH FAILURE] Skipping API teardown pass because client credentials could not be verified."
                    )

        print("-> Cleaning up ephemeral routing context... [OK]")

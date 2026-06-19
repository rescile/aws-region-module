# project/modules/vpc_endpoint_builder.py
import time

import boto3


class VPCEndpointServiceBuilder:
    def __init__(self, service_name_tag: str, region: str):
        self.ec2 = boto3.client("ec2", region_name=region)
        self.service_name_tag = service_name_tag
        self.region = region

    def _find_existing_service(self) -> dict:
        """Looks up an existing configuration by its tracking tag."""
        try:
            response = self.ec2.describe_vpc_endpoint_service_configurations(
                Filters=[{"Name": "tag:Name", "Values": [self.service_name_tag]}]
            )
            configs = response.get("ServiceConfigurations", [])
            return configs[0] if configs else None
        except Exception as e:
            print(
                f"    [ENDPOINT: AWS LOOKUP ERROR] Failed to scan endpoint services: {e}"
            )
            return None

    def build(self, nlb_arns: list) -> dict:
        """Ensures an Endpoint Service Configuration exists for Salesforce Inbound Connect."""

        # Check Idempotency
        existing_config = self._find_existing_service()
        if existing_config:
            service_id = existing_config["ServiceId"]
            service_name = existing_config["ServiceName"]
            print(
                f"    [ENDPOINT: AWS API] Endpoint Service '{self.service_name_tag}' already exists ({service_id})."
            )
            return {
                "ServiceId": service_id,
                "ServiceName": service_name,
                "Status": "EXISTING",
            }

        # ==============================================================================
        # FAST POLL WAITER: Ensure NLB is ACTIVE before associating Endpoint Service
        # ==============================================================================
        if nlb_arns:
            print(
                "⏳ [ENDPOINT: AWS API] Waiting for Network Load Balancer to become 'active'..."
            )
            elbv2 = boto3.client("elbv2", region_name=self.region)

            while True:
                try:
                    lb_description = elbv2.describe_load_balancers(
                        LoadBalancerArns=nlb_arns
                    )
                    lb_state = lb_description["LoadBalancers"][0]["State"]["Code"]

                    if lb_state == "active":
                        print(
                            "✅ [ENDPOINT: AWS API] Network Load Balancer is now ACTIVE."
                        )
                        break
                    elif lb_state == "failed":
                        raise RuntimeError(
                            "❌ [ENDPOINT: AWS API] NLB provisioning transitioned to FAILED status."
                        )

                    print(
                        f"  -> Current NLB state: '{lb_state}'. Retrying in 10 seconds..."
                    )
                    time.sleep(10)
                except Exception as wait_err:
                    print(
                        f"  -> [ENDPOINT: POLL WARNING] Waiting for target state synchronization: {wait_err}"
                    )
                    time.sleep(10)
        # ==============================================================================

        print(
            f"    [ENDPOINT: AWS API] Target missing. Creating Endpoint Service Configuration for NLBs..."
        )
        try:
            response = self.ec2.create_vpc_endpoint_service_configuration(
                NetworkLoadBalancerArns=nlb_arns,
                AcceptanceRequired=True,  # Salesforce requires manual authorization handshakes
                SupportedIpAddressTypes=["ipv4"],
            )

            service_id = response["ServiceConfiguration"]["ServiceId"]
            service_name = response["ServiceConfiguration"]["ServiceName"]

            # Tag the resource for future state discovery
            self.ec2.create_tags(
                Resources=[service_id],
                Tags=[{"Key": "Name", "Value": self.service_name_tag}],
            )

            return {
                "ServiceId": service_id,
                "ServiceName": service_name,
                "Status": "PROVISIONED",
            }
        except Exception as e:
            print(f"    [ENDPOINT: AWS ERROR] Endpoint Service creation failed: {e}")
            raise e

    def accept_inbound_connection(self, service_id: str, vpc_endpoint_id: str) -> bool:
        """Accepts the inbound connection request initiated by Salesforce Private Connect."""
        try:
            self.ec2.accept_vpc_endpoint_connections(
                ServiceId=service_id, VpcEndpointIds=[vpc_endpoint_id]
            )
            print(
                f"    [ENDPOINT: AWS API] Accepted connection request from endpoint {vpc_endpoint_id}"
            )
            return True
        except Exception as e:
            print(
                f"    [ENDPOINT: AWS ERROR] Failed to accept connection handshake: {e}"
            )
            return False

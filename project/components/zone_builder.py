# project/modules/dns_builder.py
import time

import boto3


class DNSZoneBuilder:
    def __init__(self, zone_name: str, region: str):
        self.route53 = boto3.client("route53", region_name=region)
        self.zone_name = zone_name if zone_name.endswith(".") else f"{zone_name}."
        self.region = region

    def _find_existing_zone(self, vpc_id: str) -> str:
        """Looks up an active private hosted zone matching the target name and VPC connection."""
        try:
            # Use direct list call with a max items cap instead of a broken paginator loop
            response = self.route53.list_hosted_zones_by_name(
                DNSName=self.zone_name, MaxItems="10"
            )

            for zone in response.get("HostedZones", []):
                # Ensure exact match on name string
                if zone["Name"] == self.zone_name and zone["Config"].get(
                    "PrivateZone", False
                ):
                    zone_id = zone["Id"].split("/")[-1]

                    # Verify it's tied to our specific VPC
                    zone_detail = self.route53.get_hosted_zone(Id=zone_id)
                    vpcs = zone_detail.get("VPCs", [])
                    if any(v["VPCId"] == vpc_id for v in vpcs):
                        return zone_id
            return None
        except Exception as e:
            print(f"    [DNS: AWS LOOKUP ERROR] Failed to scan zones: {e}")
            return None

    def build(self, vpc_id: str, comment: str = "") -> dict:
        """Ensures a private hosted zone exists for the given VPC namespace."""
        sanitized_comment = (
            comment.strip() if comment else "Managed by Rescile Orchestrator"
        )

        # Check idempotency: does this zone already exist for this VPC?
        existing_id = self._find_existing_zone(vpc_id)
        if existing_id:
            print(
                f"    [DNS: AWS API] Private Hosted Zone '{self.zone_name}' already exists ({existing_id}). Match found."
            )
            return {
                "HostedZoneId": existing_id,
                "Name": self.zone_name,
                "Status": "EXISTING",
            }

        print(
            f"    [DNS: AWS API] Target missing. Creating Private DNS Zone '{self.zone_name}' linked to VPC {vpc_id}..."
        )
        try:
            caller_ref = f"{self.zone_name.replace('.', '-')}-{int(time.time())}"
            response = self.route53.create_hosted_zone(
                Name=self.zone_name,
                VPC={"VPCRegion": self.region, "VPCId": vpc_id},
                CallerReference=caller_ref,
                HostedZoneConfig={
                    "Comment": sanitized_comment,
                    "PrivateZone": True,
                },
            )

            clean_zone_id = response["HostedZone"]["Id"].split("/")[-1]
            return {
                "HostedZoneId": clean_zone_id,
                "Name": self.zone_name,
                "Status": "PROVISIONED",
            }
        except Exception as e:
            print(
                f"    [DNS: AWS ERROR] Route53 zone creation failed for {self.zone_name}: {e}"
            )
            raise e

    def destroy(self, zone_id: str) -> bool:
        """Tears down the hosted zone container."""
        clean_zone_id = zone_id.strip().split("/")[-1]
        try:
            # Note: Route 53 requires a zone to be empty of custom records before deletion.
            # We will handle clearing records during the inverse dependency teardown phase.
            self.route53.delete_hosted_zone(Id=clean_zone_id)
            print(f"    [DNS: AWS API] Purged Private Hosted Zone: {clean_zone_id}")
            return True
        except Exception as e:
            print(
                f"    [DNS: AWS ERROR] Failed to terminate hosted zone {clean_zone_id}: {e}"
            )
            return False

    def upsert_alias_record(
        self, zone_id: str, record_name: str, target_dns: str, hosted_zone_id: str
    ):
        """Upserts a Route 53 private Alias record pointing to a VPC Endpoint or NLB."""
        route53 = boto3.client("route53", region_name=self.region)
        try:
            response = route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    "Comment": "Managed by Rescile: Ingress Route Plane Private Link Binding",
                    "Changes": [
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": record_name,
                                "Type": "A",
                                "AliasTarget": {
                                    "HostedZoneId": hosted_zone_id,  # For vpce, this is region-specific (e.g. Z123456789)
                                    "DNSName": target_dns,
                                    "EvaluateTargetHealth": False,
                                },
                            },
                        }
                    ],
                },
            )
            return response
        except Exception as e:
            print(f"    [DNS: AWS API ERROR] Failed to upsert DNS Alias record: {e}")
            raise e

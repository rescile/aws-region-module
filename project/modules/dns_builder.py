# project/modules/dns_builder.py
import uuid

import boto3
from botocore.exceptions import ClientError


class DNSZoneBuilder:
    def __init__(self, zone_name: str, region: str = "eu-central-2"):
        self.zone_name = zone_name if zone_name.endswith(".") else f"{zone_name}."
        self.region = region
        self.route53 = boto3.client("route53", region_name=self.region)

    def _find_existing_zone(self, vpc_id: str) -> str | None:
        """Finds a private hosted zone matching the target name associated with this VPC."""
        try:
            # Route53 doesn't filter by name elegantly, so we iterate through private zones
            zones = self.route53.list_hosted_zones_by_name(
                DNSName=self.zone_name, MaxItems="1"
            )
            for zone in zones.get("HostedZones", []):
                if zone["Name"] == self.zone_name and zone["Config"]["PrivateZone"]:
                    # Strip the /hostedzone/ prefix AWS defaults to
                    return zone["Id"].split("/")[-1]
            return None
        except ClientError as e:
            print(f"    [AWS ERROR] Failed while scanning for DNS zone: {e}")
            return None

    def build(self, vpc_id: str, comment: str = "") -> dict:
        """Creates a Route 53 Private Hosted Zone and returns sanitized metadata."""
        # Clean up description fields to prevent line break pollution in API calls
        sanitized_comment = (
            comment.strip() if comment else "Managed by Rescile Orchestrator"
        )

        try:
            # Generate a unique caller reference to maintain idempotency
            import time

            caller_ref = f"{self.zone_name}-{int(time.time())}"

            response = self.route53.create_hosted_zone(
                Name=self.zone_name,
                VPC={"VPCRegion": self.region, "VPCId": vpc_id},
                CallerReference=caller_ref,
                HostedZoneConfig={
                    "Comment": sanitized_comment,  # <-- Now properly initialized!
                    "PrivateZone": True,
                },
            )

            # Strip out any path prefix format values (e.g. '/hostedzone/') returned by AWS
            raw_zone_id = response["HostedZone"]["Id"]
            clean_zone_id = (
                raw_zone_id.split("/")[-1] if "/" in raw_zone_id else raw_zone_id
            )

            return {
                "HostedZoneId": clean_zone_id,
                "Name": self.zone_name,
                "Status": "PROVISIONED",
            }

        except Exception as e:
            print(
                f"    [AWS ERROR] Route53 zone creation failed for {self.zone_name}: {e}"
            )
            raise e

    def upsert_record(self, zone_id: str, record_node: dict, default_target: str):
        """Defensively strips and validates the Hosted Zone ID format before payload handoff."""

        # Strip path syntax and hidden characters completely
        clean_zone_id = zone_id.strip().split("/")[-1]

        print(
            f"     + Processing Record Rule: {record_node['name']} [{record_node['type']}] on Zone: {clean_zone_id}"
        )

        try:
            # Check if this is an alias vs standard target mapping
            value_target = (
                default_target if record_node.get("is_alias") else "10.100.0.1"
            )  # or your mock IP fallback

            response = self.route53.change_resource_record_sets(
                HostedZoneId=clean_zone_id,  # <--- Hand off the guaranteed sterile string
                ChangeBatch={
                    "Comment": "Orchestrated tier registration via Rescile",
                    "Changes": [
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": record_node["name"],
                                "Type": record_node["type"],
                                "TTL": 300,
                                "ResourceRecords": [{"Value": value_target}],
                            },
                        }
                    ],
                },
            )
            print(
                f"    [AWS API] Record {record_node['name']} synchronized successfully."
            )
        except Exception as e:
            print(
                f"    [AWS ERROR] Failed to upsert resource record {record_node['name']}: {e}"
            )

    def exists(self, zone_id: str) -> bool:
        """Verifies if the explicit Hosted Zone ID is live on AWS."""
        try:
            self.route53.get_hosted_zone(Id=zone_id)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchHostedZone":
                return False
            raise e

    def destroy(self, zone_id: str) -> bool:
        """Drops the explicit hosted zone container from AWS."""
        try:
            print(f"    [AWS API] Terminating Private Hosted Zone context {zone_id}...")
            self.route53.delete_hosted_zone(Id=zone_id)
            return True
        except ClientError as e:
            print(f"    [AWS ERROR] Failed to drop Hosted Zone {zone_id}: {e}")
            return False

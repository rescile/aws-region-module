# project/modules/vpc_builder.py
import boto3
from botocore.exceptions import ClientError


class VPCBuilder:
    def __init__(self, cidr: str, name: str, region: str = "eu-central-2"):
        self.cidr = cidr
        self.name = name
        self.region = region
        # Bound as self.ec2 to support core_fabric orchestrator passthrough
        self.ec2 = boto3.client("ec2", region_name=self.region)

    def _find_existing_vpc(self) -> str | None:
        """Scans the live AWS API for a VPC matching this specific deployment name tag."""
        try:
            response = self.ec2.describe_vpcs(
                Filters=[
                    {"Name": "tag:Name", "Values": [self.name]},
                    {"Name": "state", "Values": ["available", "pending"]},
                ]
            )
            vpcs = response.get("Vpcs", [])
            if vpcs:
                return vpcs[0]["VpcId"]
            return None
        except ClientError as e:
            print(
                f"    [VPC: AWS ERROR] Failed while scanning for existing infrastructure: {e}"
            )
            return None

    def build(self) -> dict:
        """Declarative alignment loop."""
        existing_vpc_id = self._find_existing_vpc()

        if existing_vpc_id:
            print(
                f"    [VPC: DECLARATIVE MATCH] VPC '{self.name}' already exists on AWS ({existing_vpc_id}). Skipping creation."
            )
            return {
                "VpcId": existing_vpc_id,
                "CidrBlock": self.cidr,
                "Name": self.name,
                "Region": self.region,
                "Status": "imported_to_state",
            }

        try:
            print(f"    [VPC: AWS API] Creating VPC ... '{self.name}' ({self.cidr})...")
            response = self.ec2.create_vpc(CidrBlock=self.cidr)
            vpc_id = response["Vpc"]["VpcId"]

            self.ec2.create_tags(
                Resources=[vpc_id], Tags=[{"Key": "Name", "Value": self.name}]
            )
            return {
                "VpcId": vpc_id,
                "CidrBlock": self.cidr,
                "Name": self.name,
                "Region": self.region,
                "Status": "newly_provisioned",
            }
        except ClientError as e:
            print(f"    [VPC: AWS ERROR] Failed to build VPC: {e}")
            raise e

    def exists(self, vpc_id: str) -> bool:
        """Checks AWS API to ensure the explicit target context actually exists."""
        try:
            self.ec2.describe_vpcs(VpcIds=[vpc_id])
            return True
        except ClientError as e:
            # Catch the specific exception AWS throws when a resource does not exist
            if e.response["Error"]["Code"] == "InvalidVpcID.NotFound":
                return False
            raise e

    def destroy(self, vpc_id: str = None) -> bool:
        """Deletes the explicit VPC resource handle from AWS."""
        # Fallback to look up by name tag if no explicit ID is passed
        target_id = vpc_id or self._find_existing_vpc()

        if not target_id:
            print(
                f"    [VPC: AWS SKIPPED] No live VPC found matching context '{self.name}' to drop."
            )
            return True

        try:
            print(f"    [VPC: AWS API] Terminating VPC context {target_id}...")
            self.ec2.delete_vpc(VpcId=target_id)
            return True
        except ClientError as e:
            print(f"    [VPC: AWS ERROR] Failed to drop VPC {target_id}: {e}")
            return False

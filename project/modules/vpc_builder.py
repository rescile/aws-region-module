# project/modules/vpc_builder.py
import boto3
from botocore.exceptions import ClientError


class VPCBuilder:
    def __init__(self, cidr: str, name: str, region: str = "eu-central-2"):
        self.cidr = cidr
        self.name = name
        self.region = region
        self.ec2_client = boto3.client("ec2", region_name=self.region)

    def _find_existing_vpc(self) -> str | None:
        """Scans the live AWS API for a VPC matching this specific deployment name tag."""
        try:
            response = self.ec2_client.describe_vpcs(
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
                f"    [AWS ERROR] Failed while scanning for existing infrastructure: {e}"
            )
            return None

    def build(self) -> dict:
        """Declarative alignment loop."""
        existing_vpc_id = self._find_existing_vpc()

        if existing_vpc_id:
            print(
                f"    [DECLARATIVE MATCH] VPC '{self.name}' already exists on AWS ({existing_vpc_id}). Skipping creation."
            )
            return {
                "VpcId": existing_vpc_id,
                "CidrBlock": self.cidr,
                "Name": self.name,
                "Region": self.region,
                "Status": "imported_to_state",
            }

        try:
            print(
                f"    [AWS API] Target missing. Creating VPC '{self.name}' ({self.cidr})..."
            )
            response = self.ec2_client.create_vpc(CidrBlock=self.cidr)
            vpc_id = response["Vpc"]["VpcId"]

            self.ec2_client.create_tags(
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
            print(f"    [AWS ERROR] Failed to build VPC: {e}")
            raise e

    def exists(self, vpc_id: str) -> bool:
        """Checks AWS API to ensure the explicit target context actually exists."""
        try:
            self.ec2_client.describe_vpcs(VpcIds=[vpc_id])
            return True
        except ClientError as e:
            # Catch the specific exception AWS throws when a resource does not exist
            if e.response["Error"]["Code"] == "InvalidVpcID.NotFound":
                return False
            raise e

    def destroy(self, vpc_id: str) -> bool:
        """Deletes the explicit VPC resource handle from AWS."""
        try:
            print(f"    [AWS API] Terminating VPC context {vpc_id}...")
            self.ec2_client.delete_vpc(VpcId=vpc_id)
            return True
        except ClientError as e:
            print(f"    [AWS ERROR] Failed to drop VPC {vpc_id}: {e}")
            return False

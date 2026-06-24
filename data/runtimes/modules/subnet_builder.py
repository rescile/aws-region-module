# project/modules/subnet_builder.py
import boto3
from botocore.exceptions import ClientError


class SubnetBuilder:
    def __init__(
        self,
        vpc_id: str,
        cidr: str,
        name: str,
        az: any = None,  # Switched to 'any' to accept graph payloads cleanly
        region: str = "eu-central-2",
    ):
        self.vpc_id = vpc_id
        self.cidr = cidr
        self.name = name
        self.region = region

        # --- DEFENSIVE GRAPHRAG DATA UNPACKING ---
        # Checks if 'az' is a nested Graph array structure like:
        # [{'node': {'name': 'eu-central-2a', ...}}]
        if isinstance(az, list) and len(az) > 0:
            node_data = az[0].get("node", {})
            self.az = node_data.get("name")
        elif isinstance(az, dict):
            self.az = az.get("node", {}).get("name")
        else:
            self.az = az  # Falls back to standard plain string or None
        # -----------------------------------------

        # Bound as self.ec2 to support core_fabric orchestrator passthrough
        self.ec2 = boto3.client("ec2", region_name=self.region)

    def _find_existing_subnet(self) -> str | None:
        """Scans AWS within the parent VPC for a subnet matching this structural name tag."""
        try:
            filters = [
                {"Name": "vpc-id", "Values": [self.vpc_id]},
                {"Name": "tag:Name", "Values": [self.name]},
                {"Name": "state", "Values": ["pending", "available"]},
            ]
            response = self.ec2.describe_subnets(Filters=filters)
            subnets = response.get("Subnets", [])
            if subnets:
                return subnets[0]["SubnetId"]
            return None
        except ClientError as e:
            print(
                f"    [SUBNET: AWS ERROR] Failed while scanning for existing subnets: {e}"
            )
            return None

    def build(self) -> dict:
        """Declarative alignment loop for the subnet resource block."""
        existing_id = self._find_existing_subnet()
        if existing_id:
            print(
                f"    [SUBNET: DECLARATIVE MATCH] Subnet '{self.name}' already exists ({existing_id}). Skipping creation."
            )
            return {
                "SubnetId": existing_id,
                "VpcId": self.vpc_id,
                "CidrBlock": self.cidr,
                "Name": self.name,
                "Region": self.region,
                "Status": "imported_to_state",
            }

        try:
            print(
                f"    [SUBNET: AWS API] Target missing. Carving Subnet '{self.name}' ({self.cidr}) inside VPC {self.vpc_id}..."
            )

            # Map parameters dynamically
            kwargs = {"VpcId": self.vpc_id, "CidrBlock": self.cidr}
            if self.az:
                kwargs["AvailabilityZone"] = self.az

            response = self.ec2.create_subnet(**kwargs)
            subnet_id = response["Subnet"]["SubnetId"]

            # Tag the resource for future convergence passes
            self.ec2.create_tags(
                Resources=[subnet_id], Tags=[{"Key": "Name", "Value": self.name}]
            )

            return {
                "SubnetId": subnet_id,
                "VpcId": self.vpc_id,
                "CidrBlock": self.cidr,
                "Name": self.name,
                "Region": self.region,
                "Status": "newly_provisioned",
            }
        except ClientError as e:
            print(
                f"    [SUBNET: AWS ERROR] Failed to allocate Subnet resource context: {e}"
            )
            raise e

    def exists(self, subnet_id: str) -> bool:
        """Checks AWS API to ensure the explicit subnet target actually exists."""
        try:
            self.ec2.describe_subnets(SubnetIds=[subnet_id])
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidSubnetID.NotFound":
                return False
            raise e

    def destroy(self, subnet_id: str = None) -> bool:
        """Drops the explicit subnet target from AWS."""
        target_id = subnet_id or self._find_existing_subnet()

        if not target_id:
            print(
                f"    [SUBNET: AWS SKIPPED] No live Subnet found matching context '{self.name}' to drop."
            )
            return True

        try:
            print(f"    [SUBNET: AWS API] Deleting Subnet context {target_id}...")
            self.ec2.delete_subnet(SubnetId=target_id)
            return True
        except ClientError as e:
            print(f"    [SUBNET: AWS ERROR] Failed to drop Subnet {target_id}: {e}")
            return False

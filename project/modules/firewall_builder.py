# project/modules/firewall_builder.py
import boto3
from botocore.exceptions import ClientError


class FirewallBuilder:
    def __init__(
        self, vpc_id: str, name: str, description: str, region: str = "eu-central-2"
    ):
        self.vpc_id = vpc_id
        self.name = name
        self.description = description
        self.region = region
        self.ec2_client = boto3.client("ec2", region_name=self.region)

    def _find_existing_sg(self) -> str | None:
        """Scans the parent VPC for a security group matching this name."""
        try:
            filters = [
                {"Name": "vpc-id", "Values": [self.vpc_id]},
                {"Name": "group-name", "Values": [self.name]},
            ]
            response = self.ec2_client.describe_security_groups(Filters=filters)
            groups = response.get("SecurityGroups", [])
            if groups:
                return groups[0]["GroupId"]
            return None
        except ClientError as e:
            print(f"    [AWS ERROR] Failed searching for security group: {e}")
            return None

    def build(self) -> dict:
        """Declarative alignment for the firewall (Security Group) container resource."""
        sg_id = self._find_existing_sg()

        if sg_id:
            print(
                f"    [DECLARATIVE MATCH] Firewall container '{self.name}' already exists ({sg_id})."
            )
            return {
                "SecurityGroupId": sg_id,
                "VpcId": self.vpc_id,
                "Name": self.name,
                "Region": self.region,
                "Status": "imported_to_state",
            }

        try:
            print(
                f"    [AWS API] Target missing. Creating Firewall Container '{self.name}' in VPC {self.vpc_id}..."
            )
            response = self.ec2_client.create_security_group(
                GroupName=self.name, Description=self.description, VpcId=self.vpc_id
            )
            sg_id = response["GroupId"]

            self.ec2_client.create_tags(
                Resources=[sg_id], Tags=[{"Key": "Name", "Value": self.name}]
            )
            return {
                "SecurityGroupId": sg_id,
                "VpcId": self.vpc_id,
                "Name": self.name,
                "Region": self.region,
                "Status": "newly_provisioned",
            }
        except ClientError as e:
            print(f"    [AWS ERROR] Failed to provision firewall container: {e}")
            raise e

    def authorize_filters(self, sg_id: str, ip_permissions: list) -> None:
        """Applies/Injects dynamic filter configuration rules into the firewall container."""
        if not ip_permissions:
            return
        try:
            print(
                f"    [AWS API] Authorizing {len(ip_permissions)} filter policy rule(s) inside {sg_id}..."
            )
            self.ec2_client.authorize_security_group_ingress(
                GroupId=sg_id, IpPermissions=ip_permissions
            )
        except ClientError as e:
            # Catch duplicate rule errors gracefully for declarative idempotency
            if e.response["Error"]["Code"] == "InvalidPermission.Duplicate":
                print(
                    f"    [DECLARATIVE MATCH] Filter rules already applied to {sg_id}. Skipping rule mutations."
                )
            else:
                print(f"    [AWS ERROR] Failed to apply filter policies: {e}")

    def exists(self, sg_id: str) -> bool:
        """Checks AWS API to verify if the explicit group ID is live."""
        try:
            self.ec2_client.describe_security_groups(GroupIds=[sg_id])
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidGroup.NotFound":
                return False
            raise e

    def destroy(self, sg_id: str) -> bool:
        """Drops the explicit security group from AWS."""
        try:
            print(f"    [AWS API] Terminating Security Group context {sg_id}...")
            self.ec2_client.delete_security_group(GroupId=sg_id)
            return True
        except ClientError as e:
            print(f"    [AWS ERROR] Failed to drop Security Group {sg_id}: {e}")
            return False

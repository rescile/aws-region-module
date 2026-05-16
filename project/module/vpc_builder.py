import boto3
from botocore.exceptions import ClientError


def get_vpc_by_name(ec2_client, ec2_resource, vpc_name):
    """
    Searches for an active VPC using its Name tag.
    Returns the boto3 Vpc resource object if found, otherwise None.
    """
    clean_name = vpc_name.strip()
    filters = [
        {"Name": "tag:Name", "Values": [clean_name, f"*{clean_name}*"]},
        {"Name": "state", "Values": ["available", "pending"]},
    ]

    try:
        vpcs = ec2_client.describe_vpcs(Filters=filters).get("Vpcs", [])
        if vpcs:
            # Return as a Resource object so the orchestrator can call .id, .load(), etc.
            return ec2_resource.Vpc(vpcs[0]["VpcId"])
        return None
    except ClientError as e:
        print(f"MODULE WARNING: Failed to lookup VPC by name: {e}")
        return None


def create_vpc(cidr_block, vpc_name, region):
    """
    Creates a new VPC if it does not already exist based on the Name tag.
    """
    session = boto3.Session(region_name=region)
    ec2_resource = session.resource("ec2")
    ec2_client = session.client("ec2")

    clean_name = vpc_name.strip()

    try:
        # Fallback check: Verify if the VPC exists via tags (in case state file is missing)
        vpc = get_vpc_by_name(ec2_client, ec2_resource, clean_name)
        if vpc:
            print(
                f"MODULE INFO: VPC '{clean_name}' already exists in AWS ({vpc.id}). Skipping creation."
            )
            return vpc

        print(
            f"MODULE CREATE: Creating new VPC '{clean_name}' ({cidr_block}) in {region}..."
        )
        vpc = ec2_resource.create_vpc(CidrBlock=cidr_block)

        # Wait until the VPC is fully initialized
        vpc.wait_until_available()

        # Tag the VPC with its designated Name
        vpc.create_tags(Tags=[{"Key": "Name", "Value": clean_name}])
        print(f"MODULE SUCCESS: VPC {vpc.id} created successfully.")
        return vpc

    except ClientError as e:
        print(f"MODULE ERROR: Failed to create VPC: {e}")
        return None


def delete_vpc(vpc_name, region):
    """
    Locates a VPC by its Name tag and attempts to delete it.
    Returns True if deleted or already gone, False if blocked by dependencies.
    """
    session = boto3.Session(region_name=region)
    ec2_resource = session.resource("ec2")
    ec2_client = session.client("ec2")

    clean_name = vpc_name.strip()

    try:
        vpc = get_vpc_by_name(ec2_client, ec2_resource, clean_name)
        if not vpc:
            print(
                f"MODULE INFO: No VPC with name '{clean_name}' found to delete. Nothing to do."
            )
            return True

        print(f"MODULE DELETE: Executing deletion for VPC '{clean_name}' ({vpc.id})...")
        vpc.delete()
        print(f"MODULE SUCCESS: VPC {vpc.id} has been removed.")
        return True

    except ClientError as e:
        if "DependencyViolation" in str(e):
            print(
                f"MODULE ABORT: VPC {vpc.id} still contains active resources (Subnets, Route Tables, ENIs) and cannot be deleted yet."
            )
        else:
            print(f"MODULE ERROR: Failed to delete VPC: {e}")
        return False

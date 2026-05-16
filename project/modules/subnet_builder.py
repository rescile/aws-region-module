import boto3
from botocore.exceptions import ClientError


def get_subnet_by_name(ec2_client, ec2_resource, subnet_name, vpc_id):
    """
    Searches for an active Subnet using its Name tag within a specific VPC.
    Returns the boto3 Subnet resource object if found, otherwise None.
    """
    clean_name = subnet_name.strip()
    filters = [
        {"Name": "tag:Name", "Values": [clean_name, f"*{clean_name}*"]},
        {"Name": "vpc-id", "Values": [vpc_id]},
        {"Name": "state", "Values": ["pending", "available"]},
    ]

    try:
        subnets = ec2_client.describe_subnets(Filters=filters).get("Subnets", [])
        if subnets:
            return ec2_resource.Subnet(subnets[0]["SubnetId"])
        return None
    except ClientError as e:
        print(f"MODULE WARNING: Failed to lookup Subnet by name: {e}")
        return None


def create_subnet(vpc_id, cidr_block, subnet_name, region, availability_zone=None):
    """
    Creates a new Subnet inside a specific VPC if it does not already exist.
    """
    session = boto3.Session(region_name=region)
    ec2_resource = session.resource("ec2")
    ec2_client = session.client("ec2")

    clean_name = subnet_name.strip()

    try:
        # Idempotency check: Verify if the Subnet already exists in this VPC
        subnet = get_subnet_by_name(ec2_client, ec2_resource, clean_name, vpc_id)
        if subnet:
            print(
                f"MODULE INFO: Subnet '{clean_name}' already exists ({subnet.id}). Skipping creation."
            )
            return subnet

        print(
            f"MODULE CREATE: Creating Subnet '{clean_name}' ({cidr_block}) inside VPC {vpc_id}..."
        )

        # Build arguments dynamically depending on whether an AZ was provided
        kwargs = {"VpcId": vpc_id, "CidrBlock": cidr_block}
        if availability_zone:
            kwargs["AvailabilityZone"] = availability_zone

        subnet = ec2_resource.create_subnet(**kwargs)

        # Tag the Subnet with its Name
        subnet.create_tags(Tags=[{"Key": "Name", "Value": clean_name}])
        print(f"MODULE SUCCESS: Subnet {subnet.id} created successfully.")
        return subnet

    except ClientError as e:
        print(f"MODULE ERROR: Failed to create Subnet: {e}")
        return None


def delete_subnet(vpc_id, subnet_name, region):
    """
    Locates a Subnet by its Name tag within a VPC and deletes it.
    Returns True if deleted or already gone, False if blocked by dependencies.
    """
    session = boto3.Session(region_name=region)
    ec2_resource = session.resource("ec2")
    ec2_client = session.client("ec2")

    clean_name = subnet_name.strip()

    try:
        subnet = get_subnet_by_name(ec2_client, ec2_resource, clean_name, vpc_id)
        if not subnet:
            print(
                f"MODULE INFO: No Subnet with name '{clean_name}' found to delete. Nothing to do."
            )
            return True

        print(
            f"MODULE DELETE: Executing deletion for Subnet '{clean_name}' ({subnet.id})..."
        )
        subnet.delete()
        print(f"MODULE SUCCESS: Subnet {subnet.id} has been removed.")
        return True

    except ClientError as e:
        print(f"MODULE ERROR: Failed to delete Subnet: {e}")
        return False

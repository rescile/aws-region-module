import boto3
from botocore.exceptions import ClientError


def get_existing_sg(ec2_resource, vpc_id, group_name):
    """
    Checks if a Security Group with the given name already exists inside the specified VPC.
    Returns the boto3 SecurityGroup resource object if found, otherwise None.
    """
    clean_name = group_name.strip()
    try:
        sgs = list(
            ec2_resource.security_groups.filter(
                Filters=[
                    {"Name": "group-name", "Values": [clean_name]},
                    {"Name": "vpc-id", "Values": [vpc_id]},
                ]
            )
        )
        return sgs[0] if sgs else None
    except ClientError as e:
        print(f"MODULE WARNING: Failed to lookup Security Group by name: {e}")
        return None


def create_security_group(vpc_id, group_name, description, region):
    """
    Creates a Security Group inside a specific VPC and attaches the inbound HTTPS filter rule.
    Returns the created/existing SecurityGroup resource object, or None if failed.
    """
    session = boto3.Session(region_name=region)
    ec2_resource = session.resource("ec2")

    clean_name = group_name.strip()

    # Idempotency check: Verify if the group already exists inside this VPC
    existing_sg = get_existing_sg(ec2_resource, vpc_id, clean_name)
    if existing_sg:
        print(
            f"MODULE INFO: Security Group '{clean_name}' already exists in VPC {vpc_id} ({existing_sg.id}). Skipping creation."
        )
        return existing_sg

    try:
        print(
            f"MODULE CREATE: Creating Security Group '{clean_name}' inside VPC {vpc_id} ({region})..."
        )
        sg = ec2_resource.create_security_group(
            GroupName=clean_name, Description=description, VpcId=vpc_id
        )

        # Tag the Security Group so it is easily identifiable in the AWS Console
        sg.create_tags(Tags=[{"Key": "Name", "Value": clean_name}])

        # Authorize inbound HTTPS traffic (TCP 443)
        print(f"MODULE CONFIG: Authorizing inbound HTTPS traffic for {sg.id}...")
        sg.authorize_ingress(
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [
                        {"CidrIp": "0.0.0.0/0"}
                    ],  # Note: Restrict this CIDR range in production environments
                }
            ]
        )
        print(f"MODULE SUCCESS: Security Group {sg.id} is fully configured.")
        return sg

    except ClientError as e:
        print(f"MODULE ERROR: Failed to create or authorize Security Group: {e}")
        return None


def delete_security_group(vpc_id, group_name, region):
    """
    Locates a Security Group by its name and VPC context, then deletes it.
    Returns True if deleted or already gone, False if blocked by dependencies.
    """
    session = boto3.Session(region_name=region)
    ec2_resource = session.resource("ec2")

    clean_name = group_name.strip()
    sg = get_existing_sg(ec2_resource, vpc_id, clean_name)

    if not sg:
        print(
            f"MODULE INFO: No Security Group named '{clean_name}' found inside VPC {vpc_id}. Nothing to delete."
        )
        return True

    try:
        print(f"MODULE DELETE: Executing deletion for Security Group {sg.id}...")
        sg.delete()
        print(f"MODULE SUCCESS: Security Group {sg.id} has been removed.")
        return True
    except ClientError as e:
        if "DependencyViolation" in str(e):
            print(
                f"MODULE ABORT: Cannot delete Security Group {sg.id}. It is still associated with a network interface (ENI) or a running instance."
            )
        else:
            print(f"MODULE ERROR: Failed to delete Security Group: {e}")
        return False

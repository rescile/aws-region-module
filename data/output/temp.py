import argparse
import sys

import boto3
from botocore.exceptions import ClientError


def get_vpc_by_name(ec2_client, ec2_resource, vpc_name):
    """Searching for a VPC based on its Name tag and returns the resource object."""
    filters = [{"Name": "tag:Name", "Values": [vpc_name]}]
    vpcs = ec2_client.describe_vpcs(Filters=filters).get("Vpcs", [])
    if vpcs:
        return ec2_resource.Vpc(vpcs[0]["VpcId"])
    return None


def create_vpc(cidr_block, vpc_name, region):
    session = boto3.Session(region_name=region)
    ec2_resource = session.resource("ec2")
    ec2_client = session.client("ec2")

    try:
        vpc = get_vpc_by_name(ec2_client, ec2_resource, vpc_name)
        if vpc:
            print(f"INFO: VPC '{vpc_name}' already exists ({vpc.id}).")
            return vpc

        print(f"CREATE: Creating VPC '{vpc_name}' ({cidr_block}) in {region}...")
        vpc = ec2_resource.create_vpc(CidrBlock=cidr_block)
        vpc.wait_until_available()
        vpc.create_tags(Tags=[{"Key": "Name", "Value": vpc_name}])

        print(f"SUCCESS: VPC {vpc.id} created.")
        return vpc
    except ClientError as e:
        print(f"ERROR during creation: {e}")
        return None


def delete_vpc(vpc_name, region):
    session = boto3.Session(region_name=region)
    ec2_resource = session.resource("ec2")
    ec2_client = session.client("ec2")

    try:
        vpc = get_vpc_by_name(ec2_client, ec2_resource, vpc_name)
        if not vpc:
            print(f"INFO: No VPC named '{vpc_name}' found. Nothing to do.")
            return True

        print(f"DELETE: Deleting '{vpc_name}' ({vpc.id})...")

        # "Standard security groups cannot be deleted,
        # but we must ensure that no other dependencies exist.
        # If you add subnets or internet gateways later,
        # these would need to be removed here BEFORE vpc.delete()."

        vpc.delete()
        print(f"SUCCESS: VPC {vpc.id} has been deleted.")
        return True

    except ClientError as e:
        if "DependencyViolation" in str(e):
            print(
                f"ABORT: Deleting VPC {vpc.id} not allowed, remaining dependencies like subnets, interfaces etc."
            )
        else:
            print(f"ERROR during deletion: {e}")
        return False


if __name__ == "__main__":
    # 1. Set up argument parser
    parser = argparse.ArgumentParser(description="Manage AWS VPC")
    parser.add_argument(
        "--delete", action="store_true", help="Deletes the VPC instead of creating it."
    )
    args = parser.parse_args()

    # 2. Variables from your Tera context
    NAME = "{{- origin_resource.name -}}"
    CIDR = "{{- origin_resource.cidr -}}"
    REGION = "{{- origin_resource.region | default(value='eu-central-2') -}}"

    # 3. Decision based on the command-line flag
    if args.delete:
        delete_vpc(NAME, REGION)
    else:
        my_vpc = create_vpc(CIDR, NAME, REGION)
        if my_vpc:
            my_vpc.reload()
            print(f"STATUS: {my_vpc.id} ist {my_vpc.state}")

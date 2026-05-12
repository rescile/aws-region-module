import boto3
from botocore.exceptions import ClientError


def create_vpc(cidr_block, vpc_name):
    # Initialize the EC2 resource
    ec2 = boto3.resource("ec2")

    try:
        # Create the VPC
        vpc = ec2.create_vpc(CidrBlock=cidr_block)

        # We wait for the VPC to exist before tagging
        vpc.wait_until_available()

        # Tag the VPC with a Name
        vpc.create_tags(Tags=[{"Key": "Name", "Value": vpc_name}])

        print(f"Successfully created VPC: {vpc.id}")
        return vpc

    except ClientError as e:
        print(f"Error creating VPC: {e}")
        return None


if __name__ == "__main__":
    # Configuration
    CIDR = "172.16.0.0/16"
    NAME = "cloud_management"

    my_vpc = create_vpc(CIDR, NAME)

    if my_vpc:
        print(f"VPC ID: {my_vpc.id}")
        print(f"State: {my_vpc.state}")

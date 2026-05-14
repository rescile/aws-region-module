import boto3
from botocore.exceptions import ClientError

def create_vpc(cidr_block, vpc_name, region):
    # Initialisiere die EC2 Resource mit einer expliziten Region
    ec2 = boto3.resource("ec2", region_name=region)

    try:
        # Create the VPC
        vpc = ec2.create_vpc(CidrBlock=cidr_block)

        # Warten, bis die VPC verfügbar ist
        vpc.wait_until_available()

        # VPC benennen
        vpc.create_tags(Tags=[{"Key": "Name", "Value": vpc_name}])

        print(f"Successfully created VPC: {vpc.id} in {region}")
        return vpc

    except ClientError as e:
        print(f"Error creating VPC: {e}")
        return None

if __name__ == "__main__":
    # Konfiguration (Werte aus deinem Template/Variablen)
    NAME = "aws_zurich_transit"
    CIDR = "10.0.0.0/24"
    REGION = "eu-central-2"

    my_vpc = create_vpc(CIDR, NAME, REGION)

    if my_vpc:
        # State neu laden, damit er nicht auf 'pending' stehen bleibt
        my_vpc.reload()
        print(f"VPC ID: {my_vpc.id}")
        print(f"State: {my_vpc.state}")
        print(f"Region: {REGION}")
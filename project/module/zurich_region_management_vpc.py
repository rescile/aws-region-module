import boto3
import sys
import argparse
from botocore.exceptions import ClientError

def get_vpc_by_name(ec2_client, ec2_resource, vpc_name):
    """Sucht eine VPC anhand des Name-Tags und gibt das Resource-Objekt zurück."""
    filters = [{'Name': 'tag:Name', 'Values': [vpc_name]}]
    vpcs = ec2_client.describe_vpcs(Filters=filters).get('Vpcs', [])
    if vpcs:
        return ec2_resource.Vpc(vpcs[0]['VpcId'])
    return None

def create_vpc(cidr_block, vpc_name, region):
    session = boto3.Session(region_name=region)
    ec2_resource = session.resource("ec2")
    ec2_client = session.client("ec2")

    try:
        vpc = get_vpc_by_name(ec2_client, ec2_resource, vpc_name)
        if vpc:
            print(f"INFO: VPC '{vpc_name}' existiert bereits ({vpc.id}).")
            return vpc

        print(f"CREATE: Erstelle VPC '{vpc_name}' ({cidr_block}) in {region}...")
        vpc = ec2_resource.create_vpc(CidrBlock=cidr_block)
        vpc.wait_until_available()
        vpc.create_tags(Tags=[{"Key": "Name", "Value": vpc_name}])

        print(f"SUCCESS: VPC {vpc.id} erstellt.")
        return vpc
    except ClientError as e:
        print(f"ERROR beim Erstellen: {e}")
        return None

def delete_vpc(vpc_name, region):
    session = boto3.Session(region_name=region)
    ec2_resource = session.resource("ec2")
    ec2_client = session.client("ec2")

    try:
        vpc = get_vpc_by_name(ec2_client, ec2_resource, vpc_name)
        if not vpc:
            print(f"INFO: Keine VPC mit Namen '{vpc_name}' gefunden. Nichts zu tun.")
            return True

        print(f"DELETE: Starte Löschvorgang für '{vpc_name}' ({vpc.id})...")

        # Standard-Sicherheitsgruppen können nicht gelöscht werden,
        # aber wir müssen sicherstellen, dass keine anderen Abhängigkeiten bestehen.
        # Falls du später Subnets oder Internet Gateways hinzufügst,
        # müssten diese hier VOR vpc.delete() entfernt werden.

        vpc.delete()
        print(f"SUCCESS: VPC {vpc.id} wurde gelöscht.")
        return True

    except ClientError as e:
        if "DependencyViolation" in str(e):
            print(f"ABORT: VPC {vpc.id} hat noch Abhängigkeiten (Subnets, Interfaces etc.) und kann nicht gelöscht werden.")
        else:
            print(f"ERROR beim Löschen: {e}")
        return False

if __name__ == "__main__":
    # 1. Argument Parser einrichten
    parser = argparse.ArgumentParser(description="Manage AWS VPC")
    parser.add_argument("--delete", action="store_true", help="Löscht die VPC statt sie zu erstellen")
    args = parser.parse_args()

    # 2. Variablen aus deinem Tera-Kontext
    NAME = "zurich_region_management"
    CIDR = "172.16.0.0/16"
    REGION = "eu-central-2"

    # 3. Entscheidung basierend auf dem Kommandozeilen-Flag
    if args.delete:
        delete_vpc(NAME, REGION)
    else:
        my_vpc = create_vpc(CIDR, NAME, REGION)
        if my_vpc:
            my_vpc.reload()
            print(f"STATUS: {my_vpc.id} ist {my_vpc.state}")
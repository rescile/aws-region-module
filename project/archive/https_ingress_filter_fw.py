import boto3
import argparse
from botocore.exceptions import ClientError

def get_vpc_details(vpc_name_query, region_fallback="eu-north-1"):
    """Findet die VPC-ID und die tatsächliche Region basierend auf dem Namen."""
    # Wir müssen eine Session starten, um zu suchen.
    # Da wir die Region noch nicht sicher wissen, nutzen wir den Fallback für den ersten Call.
    ec2_client = boto3.client("ec2", region_name=region_fallback)

    vpcs = ec2_client.describe_vpcs(
        Filters=[{'Name': 'tag:Name', 'Values': [f"*{vpc_name_query}*"]}]
    ).get('Vpcs', [])

    if not vpcs:
        # Falls in der ersten Region nichts gefunden wurde, könnte man hier
        # durch alle Regionen iterieren, aber meist reicht der Fallback.
        raise Exception(f"VPC mit Namen enthaltend '{vpc_name_query}' nicht gefunden.")

    # Wir nehmen die erste gefundene VPC
    vpc_id = vpcs[0]['VpcId']
    # Die Region ziehen wir aus der ARN oder wir bleiben beim Fallback/Session Context
    return vpc_id, region_fallback

def get_existing_sg(ec2_resource, vpc_id, group_name):
    """Prüft, ob die Security Group in der VPC bereits existiert."""
    sgs = list(ec2_resource.security_groups.filter(
        Filters=[
            {'Name': 'group-name', 'Values': [group_name]},
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ]
    ))
    return sgs[0] if sgs else None

def create_security_group(vpc_id, group_name, description, region):
    ec2 = boto3.resource('ec2', region_name=region)

    # Check ob sie schon existiert
    existing_sg = get_existing_sg(ec2, vpc_id, group_name)
    if existing_sg:
        print(f"INFO: Security Group '{group_name}' existiert bereits ({existing_sg.id}).")
        return existing_sg

    try:
        sg = ec2.create_security_group(
            GroupName=group_name,
            Description=description,
            VpcId=vpc_id
        )
        # Tags hinzufügen (wichtig für die Identifizierung später)
        sg.create_tags(Tags=[{"Key": "Name", "Value": group_name}])

        sg.authorize_ingress(
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 443,
                'ToPort': 443,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            }]
        )
        print(f"SUCCESS: Security Group erstellt: {sg.id}")
        return sg
    except ClientError as e:
        print(f"ERROR: Erstellung fehlgeschlagen: {e}")
        return None

def delete_security_group(vpc_id, group_name, region):
    ec2 = boto3.resource('ec2', region_name=region)
    sg = get_existing_sg(ec2, vpc_id, group_name)

    if not sg:
        print(f"INFO: Keine SG mit Name '{group_name}' zum Löschen gefunden.")
        return True

    try:
        print(f"DELETE: Lösche Security Group {sg.id}...")
        sg.delete()
        print("SUCCESS: Security Group gelöscht.")
        return True
    except ClientError as e:
        print(f"ERROR: Löschen nicht möglich: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--delete", action="store_true")
    args = parser.parse_args()

    # Konfiguration aus Tera
    VPC_SEARCH_NAME = "zurich_transit"
    GROUP_NAME = "https_ingress_filter"
    DESCRIPTION = "Inbound HTTPS from internal application CIDR"
    REGION_HINT = "eu-north-1"

    try:
        # 1. & 2. VPC ID und Region dynamisch ermitteln
        vpc_id, actual_region = get_vpc_details(VPC_SEARCH_NAME, REGION_HINT)

        if args.delete:
            # 4. Löschfunktion
            delete_security_group(vpc_id, GROUP_NAME, actual_region)
        else:
            # 3. Check exist & Create
            my_sg = create_security_group(vpc_id, GROUP_NAME, DESCRIPTION, actual_region)
            if my_sg:
                print(f"SG ID: {my_sg.id} in Region: {actual_region}")

    except Exception as e:
        print(f"FATAL: {e}")
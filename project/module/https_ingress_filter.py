import boto3
import argparse
from botocore.exceptions import ClientError

def get_vpc_details(vpc_name_query, region):
    # WICHTIG: Der Client MUSS die Region wissen, in der die VPC liegt
    ec2_client = boto3.client("ec2", region_name=region)

    clean_name = vpc_name_query.strip()
    print(f"DEBUG: Suche in Region '{region}' nach VPC: '{clean_name}'")

    filters = [{'Name': 'tag:Name', 'Values': [f"*{clean_name}*"]}]
    vpcs = ec2_client.describe_vpcs(Filters=filters).get('Vpcs', [])

    if not vpcs:
        raise Exception(f"VPC '{clean_name}' wurde in der Region '{region}' nicht gefunden!")

    return vpcs[0]['VpcId'], region

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

    # 1. Konfiguration aus Tera (mit .strip() um Leerzeichen zu vermeiden)
    VPC_SEARCH_NAME = "zurich_transit".strip()

    GROUP_NAME = "https_ingress_filter".strip()
    DESCRIPTION = "Inbound HTTPS from internal application CIDR"

    # 2. Region explizit setzen (Da Zürich eu-central-2 ist)
    # Wir nehmen den Wert aus dem Template, falls vorhanden, sonst Hardcode für den Test
    REGION_HINT = "eu-central-2".strip()

    # Kleiner Debug-Print (hilft enorm bei der Fehlersuche offline)
    print(f"--- Starte Script ---")
    print(f"Suche VPC: '{VPC_SEARCH_NAME}' in Region: '{REGION_HINT}'")

    try:
        # Falls VPC_SEARCH_NAME leer ist (Loop hat nichts gefunden), abbrechen
        if not VPC_SEARCH_NAME:
            raise Exception("VPC_SEARCH_NAME konnte über das Tera-Template nicht ermittelt werden!")

        # 3. VPC ID und Region dynamisch ermitteln
        # actual_region wird hier auf REGION_HINT gesetzt, damit der Client weiß, wo er suchen muss
        vpc_id, actual_region = get_vpc_details(VPC_SEARCH_NAME, REGION_HINT)

        if args.delete:
            # 4. Löschfunktion
            delete_security_group(vpc_id, GROUP_NAME, actual_region)
        else:
            # 5. Check exist & Create
            my_sg = create_security_group(vpc_id, GROUP_NAME, DESCRIPTION, actual_region)
            if my_sg:
                # reload() ist wichtig, um den aktuellen Status von AWS zu ziehen
                my_sg.load()
                print(f"SG ID: {my_sg.id} | VPC: {vpc_id} | Region: {actual_region}")

    except Exception as e:
        # Das fängt nun auch den "VPC nicht gefunden" Fehler ab
        print(f"FATAL: {e}")
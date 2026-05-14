import boto3
from botocore.exceptions import ClientError
import time

def create_phz(vpc_id, domain_name, region):
    route53 = boto3.client('route53')
    response = route53.create_hosted_zone(
        Name=domain_name,
        VPC={
            'VPCRegion': region,
            'VPCId': vpc_id
        },
        CallerReference=str(time.time()), # Unique string to prevent duplicate calls
        HostedZoneConfig={'Comment': 'Private Zone for VPC traffic', 'PrivateZone': True}
    )
    zone_id = response['HostedZone']['Id']
    print(f"Created Private Hosted Zone: {zone_id}")
    return zone_id

if __name__ == "__main__":
    # Configuration
    vpc_id = "aws_zurich_transit"
    domain_name = [my.salesforce.com]
    region = [eu-central-2]

    my_phz = create_phz(vpc_id, domain_name, region)

    if my_phz:
        print(f"DNS ID: {my_phz.id}")
        print(f"State: {my_phz.state}")
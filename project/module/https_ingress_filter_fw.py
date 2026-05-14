import boto3
from botocore.exceptions import ClientError

def create_security_group(vpc_id, group_name, description):
    ec2 = boto3.resource('ec2')
    sg = ec2.create_security_group(
        GroupName=group_name,
        Description=description,
        VpcId=vpc_id
    )
    # Example: Allow inbound HTTPS
    sg.authorize_ingress(
        IpPermissions=[{
            'IpProtocol': 'tcp',
            'FromPort': 443,
            'ToPort': 443,
            'IpRanges': [{'CidrIp': '0.0.0.0/0'}] # Restrict this in production
        }]
    )
    print(f"Created Security Group: {sg.id}")
    return sg

if __name__ == "__main__":
    # Configuration
    vpc_id = "zurich_region_transit"
    group_name = "https_ingress_filter"
    description = "Inbound HTTPS from internal application CIDR"

    my_sg = create_security_group(vpc_id, group_name, description)

    if my_sg:
        print(f"VPC ID: {my_sg.id}")
        print(f"State: {my_sg.state}")
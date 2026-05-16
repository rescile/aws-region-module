import boto3
from botocore.exceptions import ClientError

def create_eni(subnet_id, security_group_ids, description):
    ec2 = boto3.resource('ec2')
    eni = ec2.create_network_interface(
        SubnetId=subnet_id,
        Groups=security_group_ids,
        Description=description
    )
    print(f"Created ENI: {eni.id}")
    return eni

if __name__ == "__main__":
    # Configuration
    subnet_id = "transit_subnet_b"
    security_group_ids = [https_ingress_filter]
    description = "Subnet b is a logical partition of the transit network, it carves up the cloud network into smaller blocks, each with its own IP range and running in a different availability zone."

    my_nic = create_eni(subnet_id, security_group_ids, description)

    if my_nic:
        print(f"VPC ID: {my_nic.id}")
        print(f"State: {my_nic.state}")
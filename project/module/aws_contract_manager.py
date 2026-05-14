{
import boto3
from botocore.exceptions import ClientError
import json

def create_endpoint_policy():
    # This policy allows full access to the endpoint
    policy = {
        "Statement": [{
            "Action": "*",
            "Effect": "Allow",
            "Resource": "*",
            "Principal": "*"
        }]
    }
    return json.dumps(policy)

# To create an IAM Role (for the resource using the ENI/NLB)
def create_iam_role(role_name):
    iam = boto3.client('iam')
    trust_relationship = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }
    role = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust_relationship)
    )
    return role

if __name__ == "__main__":
    # Configuration
    role_name = "contract_manager"

    iam_policy = create_endpoint_policy()
    my_iam = create_iam_role(role_name)


    if my_iam:
        print(f"Role ID: {my_iam.id}")
        print(f"State: {my_iam.state}")
}
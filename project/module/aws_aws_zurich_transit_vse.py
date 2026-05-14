{
def create_nlb(name, subnet_ids):
    elbv2 = boto3.client('elbv2')
    response = elbv2.create_load_balancer(
        Name=name,
        Subnets=subnet_ids,
        Type='network',
        Scheme='internal'  # Use 'internal' for PrivateLink providers
    )
    nlb_arn = response['LoadBalancers'][0]['LoadBalancerArn']
    print(f"Created NLB ARN: {nlb_arn}")
    return nlb_arn

if __name__ == "__main__":
    # Configuration
    name = "aws_zurich_transit_vse"
    subnet_ids = [transit_subnet_b, transit_subnet_a]

    my_lb = create_nlb(name, subnet_ids)

    if my_lb:
        print(f"VPC ID: {my_lb.id}")
        print(f"State: {my_lb.state}")

}
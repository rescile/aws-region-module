import sys

import boto3
from botocore.exceptions import ClientError
from core.state_manager import get_domain_state, update_domain_state
from modules.port_filter import create_security_group, delete_security_group
from modules.subnet_builder import create_subnet, delete_subnet

# Import your atomic AWS resource module drivers
from modules.vpc_builder import create_vpc, delete_vpc, get_vpc_by_name

DOMAIN = "network"


def deploy(target_networks):
    """Orchestrates the build sequence for all configured network entries."""
    print(f"=== [DOMAIN: NETWORK] STARTING DEPLOYMENT ===")

    # Load current tracking matrix slice for the network domain
    network_state = get_domain_state(DOMAIN)

    for net in target_networks:
        name = net["name"]
        cidr = net["cidr"]
        region = net["region"]
        subnet_name = net["subnet_name"]
        subnet_cidr = net["subnet_cidr"]
        sg_name = net["sg_name"]
        sg_desc = net["sg_desc"]

        print(f"\n--> Deploying Network Node: {name} in {region}")

        # Pull existing IDs for this specific network from state if available
        net_slice = network_state.get(name, {})
        vpc_id = net_slice.get("vpc_id")
        vpc = None

        # Step 1: Handle VPC Resource Context
        if vpc_id:
            try:
                ec2_r = boto3.resource("ec2", region_name=region)
                vpc = ec2_r.Vpc(vpc_id)
                vpc.load()
            except ClientError:
                print(
                    f"WARNING: Tracked VPC ID {vpc_id} drifted from AWS. Rebuilding..."
                )
                vpc = None

        if not vpc:
            vpc = create_vpc(cidr, name, region)
            if not vpc:
                print(
                    f"FATAL: VPC creation failed for '{name}'. Aborting domain pipeline."
                )
                sys.exit(1)

        # Update temporary state storage slice
        net_slice.update({"vpc_id": vpc.id, "status": "vpc_ready"})
        network_state[name] = net_slice
        update_domain_state(DOMAIN, network_state)

        # Step 2: Handle Subnet Resource Context
        print(f"DEPLOY: Carving Subnet '{subnet_name}'...")
        subnet = create_subnet(vpc.id, subnet_cidr, subnet_name, region)
        if not subnet:
            print(f"FATAL: Subnet allocation failed for '{subnet_name}'. Aborting.")
            sys.exit(1)

        net_slice.update({"subnet_id": subnet.id, "status": "subnets_ready"})
        network_state[name] = net_slice
        update_domain_state(DOMAIN, network_state)

        # Step 3: Handle Port Filter Security Group Context
        print(f"DEPLOY: Mapping Security Group filters for '{sg_name}'...")
        sg = create_security_group(vpc.id, sg_name, sg_desc, region)
        if not sg:
            print(f"FATAL: Security Group configuration failed for '{sg_name}'.")
            sys.exit(1)

        net_slice.update({"security_group_id": sg.id, "status": "fully_deployed"})
        network_state[name] = net_slice
        update_domain_state(DOMAIN, network_state)

        print(f"SUCCESS: Network Node '{name}' is operational.")

    return get_domain_state(DOMAIN)


def teardown(target_networks):
    """Orchestrates the reverse teardown sequence for all network entries."""
    print(f"=== [DOMAIN: NETWORK] STARTING TEARDOWN ===")
    network_state = get_domain_state(DOMAIN)

    # Reverse the list evaluation order to drop dependencies safely
    for net in reversed(target_networks):
        name = net["name"]
        region = net["region"]
        sg_name = net["sg_name"]
        subnet_name = net["subnet_name"]

        print(f"\n--> Tearing Down Network Node: {name}")
        net_slice = network_state.get(name, {})
        vpc_id = net_slice.get("vpc_id")

        # Dynamic live API lookup fallback if local state trace is missing
        if not vpc_id:
            try:
                ec2_c = boto3.client("ec2", region_name=region)
                ec2_r = boto3.resource("ec2", region_name=region)
                vpc_obj = get_vpc_by_name(ec2_c, ec2_r, name)
                vpc_id = vpc_obj.id if vpc_obj else None
            except Exception:
                vpc_id = None

        # Step 1: Remove Security Groups
        if vpc_id:
            delete_security_group(vpc_id, sg_name, region)

        # Step 2: Remove Subnets
        if vpc_id:
            delete_subnet(vpc_id, subnet_name, region)
        else:
            print(
                f"WARNING: Skipping subnet cleanup; base VPC context for '{name}' was unreachable."
            )

        # Step 3: Remove Core VPC
        vpc_deleted = delete_vpc(name, region)
        if vpc_deleted:
            if name in network_state:
                del network_state[name]
            update_domain_state(DOMAIN, network_state)
            print(f"SUCCESS: Network Node '{name}' stripped cleanly.")
        else:
            print(
                f"ERROR: Retaining state token tracking for node '{name}' due to infrastructure blocks."
            )

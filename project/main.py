import argparse
import json
import os
import sys
import boto3
from botocore.exceptions import ClientError

# Import your clean AWS logic modules
from module.vpc_builder import create_vpc, delete_vpc, get_vpc_by_name
from module.subnet_builder import create_subnet, delete_subnet  # <-- NEW IMPORT
from module.https_ingress_filter_fw import create_security_group, delete_security_group

STATE_FILE = "infra_state.json"

# --- MULTI-RESOURCE STATE MANAGEMENT ---

def load_state():
    """Loads the saved infrastructure state matrix from disk."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"WARNING: {STATE_FILE} was corrupted. Initializing new state matrix.")
            return {"vpcs": {}}
    return {"vpcs": {}}

def save_state(state_data):
    """Saves the current infrastructure state matrix to disk."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state_data, f, indent=4)
    except IOError as e:
        print(f"WARNING: State could not be written to disk: {e}")

def update_vpc_state(vpc_name, vpc_id, subnet_id=None, sg_id=None, status="destroyed"):
    """Updates or deletes a specific VPC entry inside the multi-resource state matrix."""
    state = load_state()

    if status == "destroyed":
        if vpc_name in state["vpcs"]:
            del state["vpcs"][vpc_name]
    else:
        # Retain existing IDs if not overwritten by the call
        current_entry = state["vpcs"].get(vpc_name, {})
        state["vpcs"][vpc_name] = {
            "vpc_id": vpc_id if vpc_id else current_entry.get("vpc_id"),
            "subnet_id": subnet_id if subnet_id else current_entry.get("subnet_id"),
            "security_group_id": sg_id if sg_id else current_entry.get("security_group_id"),
            "status": status
        }

    if not state["vpcs"]:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    else:
        save_state(state)

# --- MAIN EXECUTION ORCHESTRATOR ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-VPC AWS Transit Hub Orchestrator")
    parser.add_argument("--delete", action="store_true", help="Tears down all configured infrastructure entries")
    args = parser.parse_args()

    # Compiling template arrays straight into a clean Python dictionary array
    # Adjust this to reflect how subnets are structurally mapped in your object schema
    TARGET_VPCS = [
        {% for net in origin_resource.network %}
        {
            "name": "{{ net.name }}".strip(),
            "cidr": "{{ net.cidr }}".strip(),
            "region": "{{ net.region | default(value='eu-central-2') }}".strip(),
            "subnet_name": "{{ net.name }}_public_subnet".strip(),
            "subnet_cidr": "{{ net.subnet_cidr | default(value='10.0.1.0/24') }}".strip(), # Tailor this fallback to your design
            "sg_name": "{{ net.name }}_https_filter".strip(),
            "sg_desc": "HTTPS ingress filter for {{ net.name }}"
        },
        {% endfor %}
    ]

    infrastructure_state = load_state()

    if args.delete:
        print(f"=== STARTING INFRASTRUCTURE TEARDOWN FOR {len(TARGET_VPCS)} NETWORKS ===")

        for target in reversed(TARGET_VPCS):
            vpc_name = target["name"]
            region = target["region"]
            sg_name = target["sg_name"]
            subnet_name = target["subnet_name"]

            print(f"\n--> Processing Teardown for Target Context: {vpc_name}")

            vpc_slice = infrastructure_state.get("vpcs", {}).get(vpc_name, {})
            vpc_id = vpc_slice.get("vpc_id")

            if not vpc_id:
                print(f"INFO: No offline state trace for {vpc_name}. Looking up via API...")
                try:
                    ec2_c = boto3.client("ec2", region_name=region)
                    ec2_r = boto3.resource("ec2", region_name=region)
                    vpc_obj = get_vpc_by_name(ec2_c, ec2_r, vpc_name)
                    vpc_id = vpc_obj.id if vpc_obj else None
                except Exception:
                    vpc_id = None

            # Step 1: Remove Security Group Dependencies
            if vpc_id:
                print(f"DELETE: Dropping Security Group '{sg_name}' from '{vpc_id}'...")
                delete_security_group(vpc_id, sg_name, region)

            # Step 2: Remove Subnet Dependencies (Must happen before VPC can be deleted!)
            if vpc_id:
                print(f"DELETE: Dropping Subnet '{subnet_name}' from '{vpc_id}'...")
                delete_subnet(vpc_id, subnet_name, region)
            else:
                print(f"WARNING: Skipping Subnet removal. Associated VPC '{vpc_name}' is unreachable.")

            # Step 3: Delete Base VPC
            print(f"DELETE: Destroying VPC target resource: '{vpc_name}'...")
            vpc_deleted = delete_vpc(vpc_name, region)

            if vpc_deleted:
                update_vpc_state(vpc_name, vpc_id=None, status="destroyed")
                print(f"SUCCESS: Network '{vpc_name}' dropped cleanly.")
            else:
                print(f"ERROR: Failed to cleanly strip infrastructure for '{vpc_name}'. Tracking record retained.")

    else:
        print(f"=== STARTING INFRASTRUCTURE DEPLOYMENT FOR {len(TARGET_VPCS)} NETWORKS ===")

        if not TARGET_VPCS:
            print("FATAL: The loop context targets evaluated to an empty sequence array. Execution halted.")
            sys.exit(1)

        for target in TARGET_VPCS:
            vpc_name = target["name"]
            cidr = target["cidr"]
            region = target["region"]
            subnet_name = target["subnet_name"]
            subnet_cidr = target["subnet_cidr"]
            sg_name = target["sg_name"]
            sg_desc = target["sg_desc"]

            print(f"\n--> Executing Deployment Pipeline for: {vpc_name} ({cidr}) in {region}")

            vpc_slice = infrastructure_state.get("vpcs", {}).get(vpc_name, {})
            vpc_id = vpc_slice.get("vpc_id")
            vpc = None

            if vpc_id:
                print(f"INFO: Validating tracking allocation trace for dynamic mapping ID: {vpc_id}...")
                try:
                    ec2_r = boto3.resource("ec2", region_name=region)
                    vpc = ec2_r.Vpc(vpc_id)
                    vpc.load()
                except ClientError:
                    print(f"WARNING: Allocated tracker ID {vpc_id} has drifted or dropped from AWS. Restoring resource context...")
                    vpc = None

            # Step 1: Network Core Instantiation (VPC)
            if not vpc:
                vpc = create_vpc(cidr, vpc_name, region)

            if not vpc:
                print(f"FATAL: Pipeline building step failed at Core Layer allocation for target '{vpc_name}'. Aborting workflow stack.")
                sys.exit(1)

            update_vpc_state(vpc_name, vpc_id=vpc.id, status="core_provisioned")

            # Step 2: Subnet Allocation (NEW STEP)
            print(f"DEPLOY: Carving Subnet '{subnet_name}' ({subnet_cidr})...")
            subnet = create_subnet(vpc.id, subnet_cidr, subnet_name, region)

            if not subnet:
                print(f"FATAL: Pipeline building step failed at Subnet allocation for target '{subnet_name}'. Aborting workflow stack.")
                sys.exit(1)

            update_vpc_state(vpc_name, vpc_id=vpc.id, subnet_id=subnet.id, status="subnet_provisioned")

            # Step 3: Security Filter Attachment
            print(f"DEPLOY: Scaling filter configuration context on '{sg_name}'...")
            sg = create_security_group(vpc.id, sg_name, sg_desc, region)

            if sg:
                update_vpc_state(vpc_name, vpc_id=vpc.id, sg_id=sg.id, status="fully_deployed")
                print(f"SUCCESS: Network array pipeline node '{vpc_name}' finalized successfully.")
                print(f"-> VPC: {vpc.id} | Subnet: {subnet.id} | SG: {sg.id}")
            else:
                print(f"ERROR: Critical fault during filtering block mapping validation for '{vpc_name}'.")
                sys.exit(1)

        print("\n=== ALL COMPONENT ENTRIES IN PIPELINE COMPLETED SUCCESSFULLY ===")

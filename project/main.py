import argparse
import sys

# Import our Domain Controllers
from orchestrators import network
# Future Imports:
# from orchestrators import storage_orch, compute_orch

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enterprise AWS Infrastructure Stack Orchestrator")
    parser.add_argument("--delete", action="store_true", help="Tears down all infrastructure blocks across all domains")
    args = parser.parse_args()

    # Tera/Jinja2 array compilation template engine block
    # This transforms your template context values straight into structured inputs
    COMPILED_NETWORK_STACK = [
        {% for net in origin_resource.network %}
        {
            "name": "{{ net.name }}".strip(),
            "cidr": "{{ net.cidr }}".strip(),
            "region": "{{ net.region | default(value='eu-central-2') }}".strip(),
            "subnet_name": "{{ net.name }}_public_subnet".strip(),
            "subnet_cidr": "{{ net.subnet_cidr | default(value='10.0.1.0/24') }}".strip(),
            "sg_name": "{{ net.name }}_https_filter".strip(),
            "sg_desc": "HTTPS ingress filter managed by automation for {{ net.name }}"
        },
        {% endfor %}
    ]

    # Future Domain Context Blocks (Storage, Compute, etc.) will be parsed here:
    # COMPILED_STORAGE_STACK = [ ... ]
    # COMPILED_COMPUTE_STACK = [ ... ]

    if args.delete:
        print("====================================================")
        print("!!! GLOBAL COMMAND INITIATED: TEARDOWN PIPELINE !!!")
        print("====================================================\n")

        # TEARDOWN ORDER: Compute -> Storage -> Network (Downstream Dependencies First)
        # print("-> Initiating Compute Domain Teardown...")
        # compute_orch.teardown(COMPILED_COMPUTE_STACK)

        # print("-> Initiating Storage Domain Teardown...")
        # storage_orch.teardown(COMPILED_STORAGE_STACK)

        print("-> Initiating Core Network Domain Teardown...")
        network_orch.teardown(COMPILED_NETWORK_STACK)

        print("\n=== GLOBAL TEARDOWN ACTIONS COMPLETED ===")

    else:
        print("====================================================")
        print("!!! GLOBAL COMMAND INITIATED: DEPLOYMENT PIPELINE !!!")
        print("====================================================\n")

        # DEPLOYMENT ORDER: Network -> Storage -> Compute (Foundation Layers First)

        # 1. Fire Network Orchestration
        active_network_state = network_orch.deploy(COMPILED_NETWORK_STACK)

        # 2. Example of Dependency Injection for future domains:
        # If your Compute Engine needs to know which VPC or Subnet ID was just built,
        # main.py passes the active_network_state directly into the next engine:
        #
        # print("-> Initiating Compute Domain Provisioning Engine...")
        # compute_orch.deploy(COMPILED_COMPUTE_STACK, network_context=active_network_state)

        print("\n=== GLOBAL DEPLOYMENT PIPELINE SCRIPT COMPLETE ===")

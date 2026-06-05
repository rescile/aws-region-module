# Rescile Project

This repository provides a blueprint for domain-driven, multi-tier infrastructure provisioning processes using Rescile's UCS. This is useful for hybrid cloud services with infrastructure growing beyond the scope of a single provider. The blueprint structures projects into common domain groups, like internet perimeter, cloud platform, cross-connect and private infrastructure. Domain groups decouple the state engine from the deployment code, collect the state from a cloud controller and integrate state signals from multiple providers. Python is used as a generic runtime to rely on provider SDK or the pulumi operator.

## Directory Structure

The project layout reflects common operational domain

```text
aws_network_hub/
├── project/
│   ├── main.py                  # Global Entry Point (Coordinates Group Orchestrators)
│   │
│   ├── core/
│   │   └── state_manager.py     # Pure State Engine (Agnostic of AWS logic)
│   │
│   ├── orchestrators/           # Tier 1: Domain Controllers
│   │   ├── network_orch.py      # Sequences VPC -> Subnet -> Security Group
│   │   ├── storage_orch.py      # Sequences S3 Buckets -> KMS Keys -> IAM
│   │   └── compute_orch.py      # Sequences Keypairs -> EC2 Instances / ASGs
│   │
│   └── modules/                 # Tier 2: Atomic AWS Resource Builders
│       ├── vpc_builder.py
│       ├── subnet_builder.py
│       ├── port_filter.py
│       └── s3_builder.py

```

## Process Sequence

The directory structure enforces a layout where responsibilities are separated into predictable layers.

```mermaid
sequenceDiagram
    autonumber
    actor User as Terminal / CI Pipeline
    participant Main as project/main.py
    participant State as core/state_manager.py
    participant Orch as orchestrators/network_orch.py
    participant Mod as modules/ (vpc / subnet / port_filter)
    participant AWS as AWS API

    User->>Main: python main.py
    Note over Main: Compiles Tera Context<br/>into COMPILED_NETWORK_STACK array
    Main->>Orch: deploy(COMPILED_NETWORK_STACK)
    
    loop For each network target in stack
        Orch->>State: get_domain_state("network")
        State-->>Orch: Return current network slice
        
        alt VPC ID not in state (New Deployment)
            Orch->>Mod: create_vpc(cidr, name, region)
            Mod->>AWS: API Call (Create & Tag)
            AWS-->>Mod: Return vpc object
            Mod-->>Orch: Return vpc object
            Orch->>State: update_domain_state("network", vpc_id, status="vpc_ready")
        else VPC ID exists in state
            Orch->>AWS: Verify resource availability (vpc.load())
        end

        Orch->>Mod: create_subnet(vpc_id, subnet_cidr, subnet_name, region)
        Mod->>AWS: API Call (Create Subnet)
        AWS-->>Mod: Return subnet object
        Mod-->>Orch: Return subnet object
        Orch->>State: update_domain_state("network", subnet_id, status="subnets_ready")

        Orch->>Mod: create_security_group(vpc_id, sg_name, sg_desc, region)
        Mod->>AWS: API Call (Create SG & Authorize Ingress)
        AWS-->>Mod: Return sg object
        Mod-->>Orch: Return sg object
        Orch->>State: update_domain_state("network", sg_id, status="fully_deployed")
    end
    
    Orch-->>Main: Return active_network_state mapping
    Note over Main: (Optional) Inject network map<br/>into compute/storage domains
    Main-->>User: Deployment Pipeline Complete
```

### 1. Entry Point

The `main.py` file represents the macro-level blueprint and handles top-level command-line flags, like `--delete`. It loads the state, calls `network_orch.deploy()`, grabs the resulting IDs, and feeds them into `compute_orch.deploy()` and coordinates the global reverse teardown (Compute $\rightarrow$ Storage $\rightarrow$ Network).

### 2. Domain Controllers 

Each domain file in the `orchestrators/` directory (e.g., `network_orch.py`) acts as the expert conductor for its specific silo. Domain controllers parse the domain-specific blocks from TOML templates and capture the tight intra-domain dependency sequencing (e.g., it calls `vpc_builder`, waits for the ID, then immediately feeds that ID into `subnet_builder` and `port_filter`). A controller returns a clean structured payload back to `main.py` and should remain provider independent.

### 3. Resource Modules

Modules remain small, generic, and hyper-focused python files. They are completely dumb to the overall business layout. A module like the `vpc_builder.py` just knows how to create or delete a VPC given a CIDR and a region. It doesn't know or care that a compute orchestrator is waiting down the line. Modules are usually defined cloud provider specific to reflect specific dependencies and requirements.

### 4. State Management

By isolating the state manager into a dedicated file in a `core/` folder, it becomes a utility that any layer can call. It reads/writes the `infra_state.json` matrix cleanly, tracking structural keys for each group (`state["network"]`, `state["storage"]`).

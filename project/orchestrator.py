import argparse
import logging
import sys

from state_manager import StateManager

# Import your specific AWS modules
try:
    from module import https_ingress_filter, zurich_transit_vpc
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import modules. Check project structure. {e}")
    sys.exit(1)

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Orchestrator")


def run_orchestration(dry_run=False):
    """
    Main sequence logic for launching Zurich Transit infrastructure.
    """
    # 1. Initialize State/Mapping file
    state = StateManager("infrastructure_state.json")

    # 2. Validation (Check if AWS matches our JSON)
    if not dry_run:
        logger.info("Verifying existing resources against AWS...")
        stale_resources = state.validate_ids()
        if stale_resources:
            logger.warning(f"Stale resources found in JSON: {stale_resources}")
            # Optional: for item in stale_resources: state.remove_resource(item)

    print("\n" + "=" * 40)
    print("  ZURICH TRANSIT VPC ORCHESTRATOR  ")
    print("=" * 40 + "\n")

    # --- STEP 1: Zurich Transit VPC ---
    vpc_name = "Zurich-Transit-VPC"
    vpc_id = state.get_id(vpc_name)

    if not vpc_id:
        logger.info(f"ACTION: Creating VPC '{vpc_name}'")
        if not dry_run:
            try:
                # Call your specific module
                vpc_id = zurich_transit_vpc.create_vpc(name=vpc_name)
                state.update_resource(vpc_name, vpc_id, "vpc")
                logger.info(f"SUCCESS: VPC created with ID {vpc_id}")
            except Exception as e:
                logger.error(f"FAILED to create VPC: {e}")
                return  # Stop orchestration if the foundation fails
        else:
            logger.info(f"[DRY-RUN] Would call zurich_transit_vpc.create_vpc()")
            vpc_id = "vpc-dry-run-placeholder"
    else:
        logger.info(f"SKIP: VPC '{vpc_name}' already exists ({vpc_id})")

    # --- STEP 2: HTTPS Ingress Filter (Security Group) ---
    sg_name = "HTTPS-Ingress-Filter"
    sg_id = state.get_id(sg_name)

    if not sg_id:
        if vpc_id:
            logger.info(f"ACTION: Creating Security Group '{sg_name}' in {vpc_id}")
            if not dry_run:
                try:
                    # Pass the vpc_id obtained from Step 1
                    sg_id = https_ingress_filter.create_security_group(
                        vpc_id=vpc_id, name=sg_name
                    )
                    state.update_resource(sg_name, sg_id, "security-group")
                    logger.info(f"SUCCESS: SG created with ID {sg_id}")
                except Exception as e:
                    logger.error(f"FAILED to create Security Group: {e}")
            else:
                logger.info(
                    f"[DRY-RUN] Would call https_ingress_filter.create_security_group()"
                )
        else:
            logger.error(
                "ERROR: Cannot create Security Group because VPC ID is missing."
            )
    else:
        logger.info(f"SKIP: SG '{sg_name}' already exists ({sg_id})")

    print("\n" + "=" * 40)
    print("  DEPLOYMENT COMPLETE  ")
    print("=" * 40)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Orchestrate AWS Zurich Transit Infrastructure"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check state and log intended actions without calling AWS",
    )

    args = parser.parse_args()

    try:
        run_orchestration(dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Unhandled Orchestrator Error: {e}")
        sys.exit(1)

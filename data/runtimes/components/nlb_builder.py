# project/modules/nlb_builder.py
import boto3


class NetworkLoadBalancerBuilder:
    def __init__(self, region: str = "eu-central-2"):
        self.elbv2 = boto3.client("elbv2", region_name=region)
        self.region = region

    def _find_existing_nlb(self, name: str) -> dict:
        """Checks if the NLB already exists to maintain idempotency."""
        try:
            response = self.elbv2.describe_load_balancers(Names=[name])
            lbs = response.get("LoadBalancers", [])
            return lbs[0] if lbs else None
        except self.elbv2.exceptions.LoadBalancerNotFoundException:
            return None
        except Exception as e:
            print(f"    [AWS LOOKUP ERROR] Failed to scan load balancers: {e}")
            return None

    def _ensure_target_group(self, name: str, vpc_id: str) -> str:
        """Ensures a TCP target group exists for the inbound Salesforce routing.

        Validates that any existing group is explicitly mapped to the active
        VPC.
        """
        tg_name = f"{name}-tg"[:32]  # AWS limits Target Group names to 32 chars
        try:
            response = self.elbv2.describe_target_groups(Names=[tg_name])
            existing_tg = response["TargetGroups"][0]

            # CRITICAL STATE SYNC CHECK: Verify VPC matching context
            if existing_tg["VpcId"] == vpc_id:
                return existing_tg["TargetGroupArn"]

            print(
                f"    ⚠️ [NLB: VPC MISMATCH] Found Target Group '{tg_name}' but it is bound to old VPC: {existing_tg['VpcId']}."
            )
            print("    -> Purging mismatched infrastructure anchor...")
            self.elbv2.delete_target_group(TargetGroupArn=existing_tg["TargetGroupArn"])

            # Raise exception to drop out into the create fallback sequence below
            raise self.elbv2.exceptions.TargetGroupNotFoundException(
                {}, "Delete Triggered Fallback"
            )

        except (self.elbv2.exceptions.TargetGroupNotFoundException, Exception) as e:
            # Swallow only the explicit 'NotFound' or our intentional deletion exception
            if "TargetGroupNotFound" not in str(
                type(e)
            ) and "Delete Triggered Fallback" not in str(e):
                raise e

            print(
                f"    [NLB: AWS API] Creating TCP Target Group '{tg_name}' inside VPC {vpc_id}..."
            )
            tg_response = self.elbv2.create_target_group(
                Name=tg_name,
                Protocol="TCP",
                Port=443,  # Salesforce HTTPS traffic standard
                VpcId=vpc_id,
                TargetType="ip",  # Using IP-based routing targets fits the graph model best
            )
            return tg_response["TargetGroups"][0]["TargetGroupArn"]

    def build(self, name: str, vpc_id: str, subnet_ids: list) -> dict:
        """Ensures an NLB and its corresponding target group are fully provisioned."""

        # 1. Check Idempotency
        existing_nlb = self._find_existing_nlb(name)
        if existing_nlb:
            nlb_arn = existing_nlb["LoadBalancerArn"]
            print(f"    [NLB: AWS API] Network Load Balancer '{name}' already exists.")

            # --- UPDATED RETURN DICTIONARY TO INCLUDE HOSTED ZONE ID ---
            return {
                "LoadBalancerArn": nlb_arn,
                "DNSName": existing_nlb["DNSName"],
                "CanonicalHostedZoneNameID": existing_nlb.get("CanonicalHostedZoneId"),
                "Status": "EXISTING",
            }

        # 2. Reconcile Target Group dependency first (Now VPC-safe)
        target_group_arn = self._ensure_target_group(name, vpc_id)

        # 3. Provision the physical NLB container
        print(
            f"    [NLB: AWS API] Target missing. Carving Network Load Balancer '{name}' across subnets..."
        )
        try:
            lb_response = self.elbv2.create_load_balancer(
                Name=name,
                Subnets=subnet_ids,
                Type="network",
                Scheme="internal",  # Must be internal for PrivateLink service attachment
                IpAddressType="ipv4",
            )
            nlb_meta = lb_response["LoadBalancers"][0]
            nlb_arn = nlb_meta["LoadBalancerArn"]

            # 4. Bind a TCP Listener to route port 443 traffic straight into our Target Group
            print(f"    [NLB: AWS API] Attaching TCP Port 443 Listener to NLB...")
            self.elbv2.create_listener(
                LoadBalancerArn=nlb_arn,
                Protocol="TCP",
                Port=443,
                DefaultActions=[
                    {"Type": "forward", "TargetGroupArn": target_group_arn}
                ],
            )

            # --- UPDATED RETURN DICTIONARY TO INCLUDE HOSTED ZONE ID ---
            return {
                "LoadBalancerArn": nlb_arn,
                "DNSName": nlb_meta["DNSName"],
                "CanonicalHostedZoneNameID": nlb_meta.get("CanonicalHostedZoneId"),
                "Status": "PROVISIONED",
            }

        except Exception as e:
            print(
                f"    [NLB: AWS ERROR] Failed to provision Network Load Balancer setup: {e}"
            )
            raise e

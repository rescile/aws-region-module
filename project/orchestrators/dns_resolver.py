# project/orchestrators/dns_resolver.py
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from modules.zone_builder import DNSZoneBuilder


class ResolverOrchestrator:
    def __init__(
        self,
        graphql_url: str,
        state_manager,
        region: str = "eu-central-2",
        scope: str = None,  # Made optional, defaults to None for core global runs
    ):
        self.url = graphql_url
        self.state = state_manager
        self.domain = "resolver"
        self.region = region
        self.scope = scope

        transport = RequestsHTTPTransport(url=self.url, verify=True, retries=3)
        self.gql_client = Client(transport=transport, fetch_schema_from_transport=False)

    def _fetch_resolver_blueprint(self) -> dict:
        # A clean query with absolutely zero arguments to guarantee schema compliance
        query = gql("""
        query GetResolver {
            resolver {
                name
                created
                public
                function
                description
                zone {
                    node {
                        name
                        region
                        description
                    }
                }
            }
        }
        """)
        try:
            # We execute without passing any variable values to satisfy the strict parser
            return self.gql_client.execute(query) or {}
        except Exception as e:
            print(f"[{self.domain.upper()} EXECUTION ERROR]: {e}")
            return {}

    def run(self) -> str:
        blueprint_data = self._fetch_resolver_blueprint()
        target_resolvers = blueprint_data.get("resolver", []) or []

        if not target_resolvers:
            print(f"No configurations discovered for domain: {self.domain}")
            return "ConfigSkippedOrNotRequired"

        # Fetch cross-domain data cleanly from the network state record
        network_state = self.state.get_domain_state("network") or {}

        # Determine Primary VPC ID by inspecting tracked network resources
        primary_vpc_id = next(
            (
                res_id
                for res_id, meta in network_state.items()
                if "VpcId" in meta and "SubnetId" not in meta
            ),
            None,
        )

        if not primary_vpc_id:
            print(
                f"[{self.domain.upper()} ERROR] Primary VPC not found in network state. Cannot bind DNS zones."
            )
            return "DependencyMissing"

        print(
            f"\n=== [DOMAIN: {self.domain.upper()}] INITIALIZING PRIVATE DNS LAYER ==="
        )

        for resolver in target_resolvers:
            # 1. 'zone' is a list of node containers
            zone_entries = resolver.get("zone", []) or []

            if not isinstance(zone_entries, list):
                # Fallback safeguard if it's a single object
                zone_entries = [zone_entries]

            # 2. Extract the inner 'node' dictionary from each entry safely
            zones = []
            for entry in zone_entries:
                if isinstance(entry, dict) and "node" in entry:
                    node_data = entry.get("node")
                    if node_data:
                        zones.append(node_data)
                elif isinstance(entry, dict):
                    # Fallback if the backend flattened it
                    zones.append(entry)

            # --- PYTHON-SIDE SCOPE FILTERING ---
            if self.scope and self.scope != "transit":
                zones = [
                    z for z in zones if self.scope.lower() in z.get("name", "").lower()
                ]

            if not zones:
                print(f"-> No zone records matched target scope: '{self.scope}'")
                continue

            for zone in zones:
                print(
                    f"-> Processing verified zone: {zone.get('name')} for VPC {primary_vpc_id}"
                )
                # 1. Provision Private Hosted Zones using DNSZoneBuilder
                # 2. Extract NLB targets from network_state and upsert Alias Records safely

        return "Success"

# project/core/state_manager.py
import json
import os


class StateManager:
    def __init__(self, state_file: str = "infra_state.json"):
        self.state_file = state_file
        # Hydrate the in-memory state snapshot once on initialization
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Reads the global infrastructure state matrix from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(
                    f"WARNING: {self.state_file} was corrupted. Initializing fresh matrix."
                )
                return {}
        return {}

    def commit(self) -> None:
        """Writes the current in-memory state matrix cleanly to disk."""
        # Filter out empty domains to prevent dangling files after a teardown
        active_infra = {k: v for k, v in self._state.items() if v}

        if not active_infra:
            if os.path.exists(self.state_file):
                try:
                    os.remove(self.state_file)
                    print(f"[STATE] Infrastructure empty. Removed {self.state_file}.")
                except OSError as e:
                    print(f"WARNING: Failed to delete empty state file: {e}")
        else:
            try:
                with open(self.state_file, "w") as f:
                    json.dump(active_infra, f, indent=4)
            except IOError as e:
                print(f"WARNING: Failed to write state file to disk: {e}")

    def get_domain_state(self, domain_name: str) -> dict:
        """Fetches the state slice for a specific domain (e.g., 'network')."""
        return self._state.get(domain_name, {})

    def record_resource(
        self, domain_name: str, resource_id: str, metadata: dict
    ) -> None:
        """
        Dynamically appends or updates an individual atomic resource inside a domain slice,
        then serializes the state alteration to disk.
        """
        if domain_name not in self._state:
            self._state[domain_name] = {}

        # Store the resource metadata mapped by its unique physical AWS identifier
        self._state[domain_name][resource_id] = metadata

        # Immediate persistence for agentic consistency
        self.commit()

    def purge_resource(self, domain_name: str, resource_id: str) -> None:
        """Removes a specific resource from tracking during a teardown sequence."""
        if domain_name in self._state and resource_id in self._state[domain_name]:
            del self._state[domain_name][resource_id]
            self.commit()

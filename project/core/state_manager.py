import json
import os

STATE_FILE = "infra_state.json"


def load_state():
    """Reads the global infrastructure state matrix from disk."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"WARNING: {STATE_FILE} was corrupted. Initializing fresh matrix.")
            return {}
    return {}


def save_state(state_data):
    """Writes the global infrastructure state matrix to disk."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state_data, f, indent=4)
    except IOError as e:
        print(f"WARNING: Failed to write state file to disk: {e}")


def get_domain_state(domain_name):
    """Fetches the state slice for a specific domain (e.g., 'network')."""
    state = load_state()
    return state.get(domain_name, {})


def update_domain_state(domain_name, domain_data):
    """Overwrites or updates data for a specific domain."""
    state = load_state()
    state[domain_name] = domain_data

    # Clean up the file entirely if all tracking domains are empty
    # This prevents leaving empty JSON files behind after a full teardown
    active_infra = {k: v for k, v in state.items() if v}
    if not active_infra:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    else:
        save_state(active_infra)

import os
import subprocess
from simple_salesforce import Salesforce

# ==============================================================================
# 1. HELPER FUNCTION TO FETCH FROM RESCILE VAULT
# ==============================================================================
def get_vault_secret(secret_name, key_name):
    """
    Executes the rescile-ce CLI command to fetch a specific secret key.
    Example: rescile-ce vault secret get "salesforce" "instance_url"
    """
    try:
        command = ["rescile-ce", "vault", "secret", "get", secret_name, key_name]
        # Run command, capture standard output, and strip whitespace/newlines
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to fetch '{key_name}' from vault '{secret_name}'.")
        print(f"CLI Error: {e.stderr.strip()}")
        raise e

# ==============================================================================
# 2. RETRIEVE CONFIGURATION FROM THE VAULT
# ==============================================================================
print("Locking into Rescile Vault to retrieve Salesforce credentials...")

# Fetching the parameters dynamically
INSTANCE_URL = get_vault_secret("salesforce", "instance_url")
CONSUMER_KEY = get_vault_secret("salesforce", "consumer_key")
SERVICE_USER = get_vault_secret("salesforce", "service_user")

# Automatically determine if we are hitting a sandbox or production
DOMAIN = "test" if "sandbox" in INSTANCE_URL.lower() else "login"

# ==============================================================================
# 3. HANDLING THE PRIVATE KEY (TWO OPTIONS)
# ==============================================================================
# OPTION A: If your 'server.key' is stored as a file locally (not tracked in Git)
PRIVATE_KEY_PATH = "server.key" 
with open(PRIVATE_KEY_PATH, "r") as key_file:
    private_key = key_file.read()

# OPTION B: If you put the raw private key text straight into the vault! (Highly Recommended)
# private_key = get_vault_secret("salesforce", "private_key")


# ==============================================================================
# 4. AUTHENTICATE AND INITIALIZE THE SDK
# ==============================================================================
try:
    sf = Salesforce(
        username=SERVICE_USER,
        consumer_key=CONSUMER_KEY,
        privatekey=private_key,
        domain=DOMAIN
    )
    print(f"🎉 Successfully authenticated! Connected to: {sf.sf_instance}")

except Exception as e:
    print(f"❌ Authentication failed: {e}")
    exit(1)

# ==============================================================================
# 5. EXECUTE YOUR API CALLS
# ==============================================================================
results = sf.query("SELECT Id, Name FROM Account LIMIT 5")
for record in results['records']:
    print(f"Account Name: {record['Name']}")

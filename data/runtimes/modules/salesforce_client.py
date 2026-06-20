# project/modules/salesforce_client.py
import time

import jwt
import requests


class SalesforceJwtClient:
    def __init__(
        self,
        consumer_key: str,
        username: str,
        private_key_string: str,
        is_sandbox: bool = True,
    ):
        self.consumer_key = consumer_key
        self.username = username

        # Ingest the raw string loaded from the environment directly
        self.private_key = private_key_string

        self.audience = (
            "https://test.salesforce.com"
            if is_sandbox
            else "https://login.salesforce.com"
        )
        self.access_token = None
        self.instance_url = None

    # project/modules/salesforce_client.py
    def authenticate(self):
        """Generates a secure, signed JWT assertion and exchanges it on-the-fly
        for a live Salesforce API access token. Zero manual tokens required.
        """
        now = int(time.time())

        # Explicitly enforce a string cast on incoming identity properties
        iss_value = str(self.consumer_key) if self.consumer_key is not None else ""
        sub_value = str(self.username) if self.username is not None else ""

        # 1. Temporary Diagnostic Print: Let's see exactly what the runtime sees
        print(f"--> [DEBUG] Type of iss: {type(iss_value)}, Value: '{iss_value}'")

        payload = {
            "iss": iss_value,  # Strictly guaranteed to be a string wrapper
            "sub": sub_value,
            "aud": self.audience,
            "exp": now + 300,
        }

        # Encode and sign the assertion using the private RS256 key
        assertion = jwt.encode(payload, self.private_key, algorithm="RS256")

        # POST the assertion directly to the Salesforce token endpoint
        token_url = f"{self.audience}/services/oauth2/token"
        payload_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }

        response = requests.post(token_url, data=payload_data)

        if response.status_code == 200:
            data = response.json()
            self.access_token = data["access_token"]
            self.instance_url = data["instance_url"]
            print("--> [AUTH: JWT] Dynamically fetched fresh execution token.")
            return self.access_token, self.instance_url
        else:
            raise Exception(
                f"❌ [AUTH: JWT FAILED] Status {response.status_code}: {response.text}"
            )

import json
import logging
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("StateManager")


class StateManager:
    def __init__(self, filename="state.json"):
        self.filename = filename
        self.state = self._load_all()

    def _load_all(self):
        if not os.path.exists(self.filename):
            return {}
        with open(self.filename, "r") as f:
            return json.load(f)

    def update_resource(self, name, resource_id, resource_type):
        """Saves ID with extra metadata."""
        self.state[name] = {
            "id": resource_id,
            "type": resource_type,
            "created_at": datetime.now().isoformat(),
            "status": "active",
        }
        self._save_all()

    def get_id(self, name):
        """Helper to get just the ID string."""
        record = self.state.get(name)
        return record["id"] if record else None

    def _save_all(self):
        with open(self.filename, "w") as f:
            json.dump(self.state, f, indent=4)

    def validate_ids(self):
        """Checks AWS to see if the stored IDs actually still exist."""
        ec2 = boto3.client("ec2")
        invalid_resources = []

        logger.info("Validating local state against AWS...")

        for name, data in self.state.items():
            res_id = data["id"]
            res_type = data["type"]

            try:
                if res_type == "vpc":
                    ec2.describe_vpcs(VpcIds=[res_id])
                elif res_type == "subnet":
                    ec2.describe_subnets(SubnetIds=[res_id])
                # Add more types as needed (igw, security-group, etc.)
            except ClientError:
                logger.warning(f"Resource {name} ({res_id}) not found in AWS!")
                invalid_resources.append(name)

        return invalid_resources

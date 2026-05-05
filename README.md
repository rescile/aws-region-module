# AWS Transit Hub
A Transit Hub is a small AWS account designed that connects SaaS hosted on amazon (e.g. Salesforce, Databricks) via private gateways and under a governed security model. While a VPC in an existing account lacks inherent guardrails, this purpose build landing zone ensures that the network environment is pre-configured for compliance, centralized logging, and identity management before external services are connected. This transit zone serves as the administrative and technical boundary where the AWS network meets the service provider endpoint. 

## Technical Components

| Category | Resource Name | Purpose |
| :--- | :--- | :--- |
| **Compute** | Elastic Network Interface (ENI) | The physical "landing zone" for private IPs in your subnets. |
| **Load Balancing**| Network Load Balancer (NLB) | Necessary for "Outbound" connections (Provider → AWS). |
| **Security** | Security Groups | Controls which internal resources can "talk" to the service provider. |
| **Identity** | IAM Role / Endpoint Policy | Governs permissions for the PrivateLink connection. |
| **DNS** | Route 53 PHZ | Redirects service provider traffic to the private network. |


### Networking Foundation (VPC)
*   *Virtual Private Cloud (VPC):* A logically isolated virtual network with a non-overlapping CIDR block (e.g., `/16` or `/24`).
*   *Private Subnets:* At least two subnets in different Availability Zones (AZs) for high availability. These subnets host the ENIs for the connection and should have no route to an Internet Gateway.
*   *Route Tables:* Specifically configured to route internal traffic within the VPC and through the VPC endpoints rather than out to the public internet.

### Connectivity Resources (PrivateLink)
The specific resource depends on whether the traffic is coming *from* the service provider or going *to* the service provider:

#### Inbound
*Interface VPC Endpoint:* This resource is created using the service name provided by the service provider. It generates *Elastic Network Interfaces (ENIs)* in your private subnets with private IP addresses that represent the service provider API.
#### Outbound
* *VPC Endpoint Service:* This exposes your internal AWS service (like an API Gateway or a private application) to the service provider network.
* *Network Load Balancer (NLB):* Required to sit in front of your application. The Endpoint Service points to this NLB, which then distributes traffic to your backend resources (EC2, Lambda, or ALB).

### Security & Governance
* *Security Groups:* Acts as a stateful firewall for the VPC Endpoint ENIs. You must explicitly allow inbound traffic on **Port 443** from the specific CIDR ranges of your application servers.
* *VPC Endpoint Policy:* An IAM-style JSON policy attached directly to the Interface Endpoint to restrict which AWS principals can use the connection and which Salesforce actions they can perform.
* *VPC Flow Logs:* For auditability, logs should be enabled to capture all IP traffic directed toward the Salesforce termination point.

### Name Resolution
*Route 53 Private Hosted Zone (PHZ):* This allows your AWS resources to resolve the service provider DNS name (e.g., `your-org.my.saas.com`) to the *private IP addresses* of your VPC Endpoint instead of the public internet IPs.

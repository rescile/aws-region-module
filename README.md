# AWS Network Hub
A Network Hub is a small AWS account designed that connects SaaS hosted on amazon (e.g. Salesforce, Databricks) via private gateways and under a governed security model. While a VPC in an existing account lacks inherent guardrails, this purpose build landing zone ensures that the network environment is pre-configured for compliance, centralized logging, and identity management before external services are connected. This transit zone serves as the administrative and technical boundary where the AWS network meets the service provider endpoint. 

## Private Connectivity

SaaS provider require a *VPC Endpoint Interface* within a private subnet to serve regulated industries like banking, insurance and healthcare. A transit network is the prerequisite infrastructure that transforms a network gateway into a secure node, capable of supporting private, non-internet-routable peering with the provider. The network hub acts as deployment zone for private termination points. It provides a VPC structure, with no logical location to assign the private IP addresses required for the two networks to "see" each other. This setup enables the following services:

### Network Address Translation (NAT) and Routing
The network zone enables cloud service integrations via private IP addressing, hence traffic does not traverse the public internet via standard HTTPS/TLS over an Internet Gateway, it utilizes *unroutable private IP addresses*. 

### Encapsulation of the Security Perimeter
By terminating the connection in a controlled zone, organizations can apply *Stateful Firewalls* (Security Groups) and *Stateless Filters* (Network ACLs) directly to the endpoint. This ensures that if a resource within the cloud environment is compromised, the threat cannot move laterally into the Salesforce environment, as the landing zone acts as a strictly governed gateway.

### Resolution of Private DNS Namespaces
Public instances of services like Salesforce resolve to public IP addresses. When moving to a private connection, the system must resolve to a private IP within the VPC. The transit network provides the *Private DNS Zone* infrastructure. This infrastructure intercepts requests for the SaaS provider and redirects them to the private termination point, ensuring that data remains on the internal backbone.

### Auditability and Traffic Symmetrics
Regulatory frameworks (such as SOC2, HIPAA, or GDPR) often require proof of data transit paths. A network hub provides a centralized point for *VPC Flow Logs*. This captures every packet entering or leaving the Salesforce connection. Without this formal termination point, traffic monitoring becomes fragmented, making it difficult to verify that data has remained off the public internet during a compliance audit.

## Technical Components

| Category | Resource Name | Purpose |
| :--- | :--- | :--- |
| **Compute** | Elastic Network Interface (ENI) | The physical "landing" point for private IPs in your subnets. |
| **Load Balancing**| Network Load Balancer (NLB) | Necessary for "Outbound" connections (Salesforce → AWS). |
| **Security** | Security Groups | Controls which internal resources can "talk" to Salesforce. |
| **Identity** | IAM Role / Endpoint Policy | Governs permissions for the PrivateLink connection. |
| **DNS** | Route 53 PHZ | Redirects Salesforce traffic to the private network. |


### Networking Foundation (VPC)
*   *Virtual Private Cloud (VPC):* A logically isolated virtual network with a non-overlapping CIDR block (e.g., `/16` or `/24`).
*   *Private Subnets:* At least two subnets in different Availability Zones (AZs) for high availability. These subnets host the ENIs for the connection and should have no route to an Internet Gateway.
*   *Route Tables:* Specifically configured to route internal traffic within the VPC and through the VPC endpoints rather than out to the public internet.

### Connectivity Resources (PrivateLink)
The specific resource depends on whether the traffic is coming *from* Salesforce or going *to* Salesforce:

*   Inbound (AWS to Salesforce):
    *   *Interface VPC Endpoint:* This resource is created using the service name provided by Salesforce. It generates *Elastic Network Interfaces (ENIs)* in your private subnets with private IP addresses that represent the Salesforce API.
*   Outbound (Salesforce to AWS):
    *   *VPC Endpoint Service:* This exposes your internal AWS service (like an API Gateway or a private application) to the Salesforce network.
    *   *Network Load Balancer (NLB):* Required to sit in front of your application. The Endpoint Service points to this NLB, which then distributes traffic to your backend resources (EC2, Lambda, or ALB).

### Security & Governance
*   *Security Groups:* Acts as a stateful firewall for the VPC Endpoint ENIs. You must explicitly allow inbound traffic on **Port 443** from the specific CIDR ranges of your application servers.
*   *VPC Endpoint Policy:* An IAM-style JSON policy attached directly to the Interface Endpoint to restrict which AWS principals can use the connection and which Salesforce actions they can perform.
*   *VPC Flow Logs:* For auditability, logs should be enabled to capture all IP traffic directed toward the Salesforce termination point.

### Name Resolution
*   *Route 53 Private Hosted Zone (PHZ):* This allows your AWS resources to resolve the Salesforce DNS name (e.g., `your-org.my.salesforce.com`) to the *private IP addresses* of your VPC Endpoint instead of the public internet IPs.

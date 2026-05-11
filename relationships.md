# OSCAL Relationship Mapping for Infrastructure & Platform Deployments

This document outlines the standard and extended relationships within OSCAL (Open Security Controls Assessment Language) tailored for infrastructure provisioning, platform engineering, and cloud-native deployments.

## 1. Structural & Authoritative Relationships
These define the "Source of Truth." In provisioning, these link your code or infrastructure back to the regulatory requirements.

| Relation / Type | Description | Infrastructure & Platform Use Case |
| :--- | :--- | :--- |
| **DEFINED_BY** | Links a specific implementation to its governing policy or standard. | A Terraform module for an S3 bucket is **DEFINED_BY** the "Data Encryption at Rest" policy. |
| **DERIVED_FROM** | Shows inheritance, specifically when a specialized profile stems from a base catalog. | A "Hardened Kubernetes Profile" is **DERIVED_FROM** the NIST 800-53 Rev 5 catalog. |
| **SATISFIES** | Maps a component's function to a specific control requirement. | An AWS KMS key **SATISFIES** the requirement for cryptographic protection (SC-28). |

## 2. Dependency & Composition Relationships
These describe the "Stack." They are essential for modeling shared responsibility in cloud-native environments (e.g., App → K8s → EC2).

| Relation / Type | Description | Infrastructure & Platform Use Case |
| :--- | :--- | :--- |
| **DEPENDS_ON** | Indicates a hard functional dependency where one cannot operate without the other. | A Microservice **DEPENDS_ON** an RDS instance for state; the deployment fails if the DB is absent. |
| **COMPOSED_OF** | Aggregates multiple small components into a single logical system. | A "Logging Stack" is **COMPOSED_OF** FluentBit, OpenSearch, and Dashboards. |
| **PROVIDED_BY** | Indicates a capability inherited from a parent platform or provider (Leveraged Authorization). | Identity management for a Pod is **PROVIDED_BY** the EKS OIDC provider (Shared Responsibility). |

## 3. Implementation & Responsibility Relationships
These answer: *What is doing the work, and who owns it?*

| Relation / Type | Description | Infrastructure & Platform Use Case |
| :--- | :--- | :--- |
| **IMPLEMENTED_BY** | The primary link between a control and the technical "mechanism" (the component). | MFA requirements are **IMPLEMENTED_BY** the Okta Terraform provider configuration. |
| **RESPONSIBLE_FOR** | Maps a human or machine `role` to a specific task or control. | The "Platform Engineering Team" is **RESPONSIBLE_FOR** patching the underlying AMI. |
| **DEPLOYED_VIA** | Connects a component to its orchestration or CI/CD source. | A VPC is **DEPLOYED_VIA** GitHub Actions; this provides the audit trail for "who changed what." |

## 4. Connectivity & Data Flow Relationships
These describe the "Network Fabric." They are vital for generating automated firewall rules or Network Policies.

| Relation / Type | Description | Infrastructure & Platform Use Case |
| :--- | :--- | :--- |
| **CONNECTS_TO** | Describes a network-level path or peering relationship. | A VPC in `us-east-1` **CONNECTS_TO** a Transit Gateway to reach the corporate data center. |
| **EXCHANGES_DATA** | Defines the protocol and type of data moving between two endpoints. | An App **EXCHANGES_DATA** with a Redis cache via TLS over port 6379. |
| **PROTECTS** | Specifically used for security tooling (WAF, IPS, etc.). | A CloudArmor Policy **PROTECTS** the Load Balancer from Layer 7 DDoS attacks. |

## 5. Evidence & Traceability Relationships
These provide the "Audit Trail" required for continuous compliance and ATO (Authority to Operate).

| Relation / Type | Description | Infrastructure & Platform Use Case |
| :--- | :--- | :--- |
| **EVIDENCED_BY** | Links a control to a specific point-in-time output (log, screenshot, JSON). | The "Encrypted" status of a volume is **EVIDENCED_BY** a daily AWS Config snapshot. |
| **VERIFIED_BY** | Connects a control to the test or scan that validated its state. | A network isolation control is **VERIFIED_BY** a Checkov/Terrascan static analysis pass. |
| **DOCUMENTED_IN** | Points to the README, Wiki, or architectural decision record (ADR). | The failover logic for a multi-region deployment is **DOCUMENTED_IN** the Disaster Recovery Plan. |

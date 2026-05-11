# OSCAL

## Structural / Authoritative Relationships

These define where something comes from or what defines it.

| ... | Relations | Remark |
| :---: | :--- | :--- |
| **DEFINED_BY** | Control implementation → policy, standard, or procedure; Component → architecture definition or baseline | Example: Control AC-2 implementation DEFINED_BY Access Control Policy |
| **DERIVED_FROM** | Tailored control → baseline control (e.g. NIST SP 800-53), Parameterized control → generic control definition | Useful for overlays and profiles |
| **GOVERNED_BY** | System or component → policy or regulatory framework | Often links to: ISO/IEC 27001, Internal security policies |

## Dependency & Composition Relationships

These capture how system elements rely on each other.

| ... | Relations | Remark |
| :---: | :--- | :--- |
| **DEPENDS_ON** | Service → infrastructure component; Control → external system capability | Example: Backup Service DEPENDS_ON Object Storage |
| **COMPOSED_OF** | System → subsystems; Component → subcomponents | Helps model layered architectures |
| **HOSTED_ON** | Application → VM / container platform / Kubernetes node | Common in cloud-native SSPs |
| **RUNS_ON** | Application → VM / container platform / Kubernetes node | Common in cloud-native SSPs |

## Implementation & Responsibility Relationships

These map controls to actual enforcement points.

| ... | Relations | Remark |
| :---: | :--- | :--- |
| **IMPLEMENTED_BY** | Control → component or service; One of the most critical SSP relationships | Example: IA-2 IMPLEMENTED_BY Identity Provider |
| **PROVIDED_BY** | Capability → shared service (e.g., IAM, logging platform) | Frequently used in hybrid/cloud SSPs |
| **RESPONSIBLE_FOR** | Role or team → control or component | Useful for operational accountability (not always explicit in OSCAL, but often modeled via props/links) |

## Data Flow & Interaction Relationships

These describe runtime behavior and integration. |

| ... | Relations | Remark |
| :---: | :--- | :--- |
| CONNECTS_TO | Network-level relationships | Often complements diagrams rather than replaces them |
| EXCHANGES_DATA_WITH | Application ↔ application | Important for: data classification and trust boundaries |
| PROTECTS / MONITORS | Security service → protected asset | Example: WAF PROTECTS Web Application, SIEM MONITORS Infrastructure |

## Evidence & Traceability Relationships

Critical for auditability and continuous compliance.

| ... | Relations | Remark |
| :---: | :--- | :--- |
| **EVIDENCED_BY** | Control implementation → evidence artifact (logs, reports) | |
| **VERIFIED_BY** | Control → assessment procedure or test case | |
| **DOCUMENTED_IN** | Component or control → documentation artifact | |

## Lifecycle & Operational Relationships

Less standardized but increasingly important.

| ... | Relations | Remark |
| :---: | :--- | :--- |
| **MANAGED_BY** | Component → platform team or automation system | |
| **DEPLOYED_VIA** | Component → CI/CD pipeline | |
| **BACKED_UP_BY** | Data store → backup system | |

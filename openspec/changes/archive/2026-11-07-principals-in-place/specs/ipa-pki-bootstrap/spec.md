# Spec Delta: ipa-pki-bootstrap

## ADDED Requirements

### Requirement: CA ACL host grants precede any self-enrollment
The CA ACL host grants that authorize kube hosts to self-enroll (`kubernetes-ca-acl`, `kubeclusteradm-acl`) SHALL be applied on the IPA server within the CA provisioning chain — after the two CAs and their profiles exist and **before** any master or worker self-enrollment task runs. The profile user category does not cover host principals, so self-enrollment MUST NOT rely on a later task for these grants.

#### Scenario: Fresh converge grants hosts before join
- **WHEN** a fresh converge provisions the cluster and reaches the first node (or master) certificate self-enrollment
- **THEN** every kube host that will self-enroll is already a member of the relevant CA ACL, and the enrollment succeeds without any admin-identity fallback

#### Scenario: Late grant is repaired on next converge
- **WHEN** a host is added to the inventory after the CA chain last ran and its ACL grant is missing
- **THEN** the pre-join CA-ACL step of the next converge adds the host before its self-enrollment runs, using the check-then-add pattern (no failure when already a member)

#### Scenario: Grants do not stall on absent nodes
- **WHEN** the CA-ACL grant step runs during the CA chain on the IPA server
- **THEN** it authenticates with the IPA server's own admin scratch ticket and does not depend on any kube host being reachable

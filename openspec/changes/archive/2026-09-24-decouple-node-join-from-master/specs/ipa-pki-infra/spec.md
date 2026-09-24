## ADDED Requirements

### Requirement: KubeNodes cert profile is created
The system SHALL create a `kubernetesNodes` certificate profile with `O=system:nodes` in the subject organization field, for worker-node client certificates.

#### Scenario: Cert profile is created
- **WHEN** the role runs and no `kubernetesNodes` profile exists
- **THEN** the profile is imported with `O=system:nodes` in the name parameter
- **THEN** the profile is linked to the `kubernetes-ca` via the CA ACL

#### Scenario: Cert profile already exists
- **WHEN** the role runs and the `kubernetesNodes` profile already exists
- **THEN** no profile import is performed and the task reports no change

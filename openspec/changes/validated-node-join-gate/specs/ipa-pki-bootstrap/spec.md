# Spec Delta

## MODIFIED Requirements

### Requirement: API server serves traffic after PKI swap
After the static pods are restarted following the PKI certificate swap, the system SHALL verify that the API server is healthy and that its serving certificate chains to the expected trust anchor before proceeding. Readiness polling SHALL be a TLS-validated healthz check against a SAN-matching API address, anchored to the CA the API is expected to present at that point in the sequence.

#### Scenario: API server ready after swap
- **WHEN** the role runs on a master and the API server static pod has been restarted with new certificates
- **THEN** the healthz endpoint returns 200 over a TLS-validated connection anchored to the expected CA (retried until available)
- **THEN** the controller manager holds a fresh leader lease before the swap phase proceeds

#### Scenario: Old-certificate window gate validates against the merged bundle
- **WHEN** the API server is restarted after the kubeconfig and manifest edits, before the IPA-signed serving certificate exists
- **THEN** the readiness gate validates the presented serving certificate against the merged CA bundle (kubeadm + IPA)
- **THEN** the gate passes whether the API presents the old or the new serving certificate

#### Scenario: New-certificate gate asserts the transition completed
- **WHEN** the API server is restarted to pick up the IPA-signed serving certificate
- **THEN** the readiness gate validates the presented serving certificate against the IPA CA only
- **THEN** the gate passes only when the running server presents the new certificate

#### Scenario: Gate failure surfaces a diagnostic and fails the run
- **WHEN** the readiness gate observes that the API server still presents the old (kubeadm) serving certificate after the restart window elapses
- **THEN** the task reports which certificate is presented, its issuer, and the expected issuer before failing the playbook

#### Scenario: Post-swap stabilization is a single validated gate
- **WHEN** the PKI swap phase confirms the cluster is stable after kubeconfig and URL re-pointing
- **THEN** a single TLS-validated healthz check anchored to the IPA CA confirms the API is healthy and presents the IPA-CA-anchored serving certificate

### Requirement: Node join validates the presented CA before joining
A node SHALL NOT execute `kubeadm join` until it has verified that the master's kube-apiserver serves a certificate chain rooted at the expected trust anchor. The check SHALL be a TLS-validated connection from the node to the API server address, anchored to the CA bundle the node is expected to trust after the PKI swap (the IPA CA). Join-time verification SHALL use the same join-time hash computation as the join command so that a mismatch between the presented chain and the join configuration fails before any cluster state is written.

#### Scenario: Node joins only against an IPA-anchored API
- **WHEN** a node reaches the join phase after the master's PKI swap has completed
- **THEN** the node validates a TLS connection to the API server anchored to the IPA CA before running `kubeadm join`
- **THEN** the join proceeds only when the presented serving certificate chains to the IPA CA

#### Scenario: Join is refused when the API still presents the old chain
- **WHEN** a node reaches the join phase but the master's API server still serves the pre-swap (kubeadm) serving certificate
- **THEN** the TLS validation anchored to the IPA CA fails and `kubeadm join` is not executed

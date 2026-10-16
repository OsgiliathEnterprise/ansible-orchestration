# Spec Delta

## MODIFIED Requirements

### Requirement: Node join waits for API server readiness
A worker node SHALL wait until the Kubernetes API server reports healthy before configuring kubelet credentials and starting the kubelet. The readiness gate SHALL verify the API server's serving certificate chains to the node's own trust anchor, and the trust anchor SHALL be installed on the node from FreeIPA before the gate runs.

#### Scenario: Join gated on healthz
- **WHEN** a worker node is ready to join but the API server is not yet reachable
- **THEN** the join step retries until `https://<api>:6443/healthz` returns 200
- **THEN** kubelet credentials are configured only after readiness is confirmed

#### Scenario: Readiness gate verifies TLS trust against the node's own CA
- **WHEN** a worker node runs the API readiness gate
- **THEN** the healthz poll verifies the API server's serving certificate against the node's locally installed trust anchor
- **THEN** the gate passes only when the API is reachable and its certificate chains to that trust anchor
- **THEN** the trust anchor verified by the gate is the same CA the node commits to its kubelet configuration

#### Scenario: Trust anchor mismatch fails fast at the gate
- **WHEN** the API server serves a certificate that does not chain to the node's trust anchor (e.g. the master was re-initialized after the node's anchor was fetched)
- **THEN** the readiness gate fails with a TLS verification error at the top of the join block
- **THEN** no drop-in surgery, kubelet state reset, or kubelet restart occurs before the failure surfaces

#### Scenario: Trust anchor survives node state reset
- **WHEN** the join block resets kubeadm state after the readiness gate passes (the reset wipes `/etc/kubernetes/pki/`)
- **THEN** the trust anchor is reinstalled on the node from the verified fetch before kubelet configuration proceeds
- **AND** kubelet starts with a valid `certificate-authority` file present

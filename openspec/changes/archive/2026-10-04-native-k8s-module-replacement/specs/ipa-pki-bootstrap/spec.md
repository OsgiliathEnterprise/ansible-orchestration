## MODIFIED Requirements

### Requirement: Pre-existing Calico/Tigera workloads trust the post-swap CA
After the PKI swap replaces `/etc/kubernetes/pki/ca.crt` and restarts control-plane static pods, the system SHALL rolling-restart the pre-existing `calico-node` DaemonSet (`calico-system`) so each node's in-cluster `ca.crt` is re-materialized with the post-swap CA. The trigger SHALL fire only when the workload does not yet reflect the current post-swap CA; a re-converge with an unchanged CA SHALL be a no-op.

#### Scenario: calico-node pods refreshed after swap
- **WHEN** the PKI swap has completed and control-plane components report Ready
- **THEN** each node's `calico-node` pod is rolling-restarted so it mounts the post-swap in-cluster CA
- **THEN** a `calico-node` pod is present and Ready on every node (master and workers)

#### Scenario: Recovery is idempotent
- **WHEN** converge runs again and the `calico-node` pods already trust the post-swap CA
- **THEN** the recovery step does not fail or churn the workloads unnecessarily

#### Scenario: CA rotation re-triggers recovery
- **WHEN** the post-swap CA changes after a previous recovery already ran against an earlier CA
- **THEN** the `calico-node` workload is rolling-restarted again so it picks up the new CA

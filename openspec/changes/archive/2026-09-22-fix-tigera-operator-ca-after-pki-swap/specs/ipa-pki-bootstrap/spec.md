# Spec Delta

## ADDED Requirements

### Requirement: Pre-existing Calico/Tigera workloads trust the post-swap CA
After the PKI swap replaces `/etc/kubernetes/pki/ca.crt` and restarts the control-plane static pods, the system SHALL rolling-restart the pre-existing `calico-node` DaemonSet (in `calico-system`) so that kubelet re-materializes each node's in-cluster `ca.crt` with the post-swap CA. This ensures CNI initialises on every node instead of worker nodes staying `NotReady`.

#### Scenario: calico-node pods refreshed after swap
- **WHEN** the PKI swap has completed and control-plane components report Ready
- **THEN** each node's `calico-node` pod is rolling-restarted so it mounts the post-swap in-cluster CA
- **THEN** a `calico-node` pod is present and Ready on every node (master and workers)

#### Scenario: Recovery is idempotent
- **WHEN** converge runs again and the `calico-node` pods already trust the post-swap CA
- **THEN** the recovery step does not fail or churn the workloads unnecessarily

### Requirement: Converge waits for per-node CNI readiness after swap
After rolling-restarting the `calico-node` DaemonSet, the system SHALL wait until a `calico-node` pod is present and Ready on every node before the converge phase completes. This guarantees worker-node CNI is initialized so nodes reach `Ready`.

#### Scenario: calico-node deployed to all nodes
- **WHEN** the rolling restart has completed after the swap
- **THEN** a `calico-node` pod exists and is Ready on each node (master and workers) before converge completes

#### Scenario: CNI not ready in time
- **WHEN** a `calico-node` pod has not become Ready on some node within the readiness timeout
- **THEN** converge fails with an error naming the affected node(s)

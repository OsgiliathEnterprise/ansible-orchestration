# Proposal

## Why

The `ipa-pki-bootstrap` swap replaces `/etc/kubernetes/pki/ca.crt` (the kubeadm CA) with the FreeIPA `kubernetes-ca`, then restarts the API server / controller-manager / scheduler static pods and refreshes the kubelet. Control-plane components recover, but **data-plane workloads that were already running before the swap — most critically the per-node `calico-node` pods — keep their stale in-cluster `ca.crt`** (kubelet materializes that file at pod-creation time). With a stale CA, CNI does not initialise on worker nodes. Workers therefore stay `NotReady` even though the control plane is healthy — breaking the converged end-state that `restart-resilience` expects.

## What Changes

- After the PKI swap stabilizes the control plane, **rolling-restart the pre-swap `calico-node` DaemonSet** (in `calico-system`) so kubelet re-materializes each node's in-cluster `ca.crt` with the post-swap CA and CNI initialises.
- Wait for a `calico-node` pod to be present and Ready on every node before the converge phase completes, so worker CNI is initialized and nodes reach `Ready`.
- No change to how the swap generates/replaces certificates or restarts control-plane static pods; this only adds data-plane workload recovery after those steps.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ipa-pki-bootstrap`: add a requirement that the pre-existing `calico-node` DaemonSet is rolling-restarted after the PKI swap so each node re-materializes the post-swap CA, and that converge waits for a Ready `calico-node` pod on every node before completing.

## Impact

- `tasks/ipa-pki-swap.yml`: add a post-stabilization step to rolling-restart the `calico-node` DaemonSet and wait for per-node `calico-node` readiness (new included task file `tasks/calico-ca-recovery.yml`).
- Converge end-state: worker nodes reach `Ready` after converge; unblocks `test_node_ready_via_master_admin_conf`.
- No API/dependency changes; purely additive recovery step in the existing swap flow.

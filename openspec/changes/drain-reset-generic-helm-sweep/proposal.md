# Drain-Reset Generic Helm Sweep

## Why

The destroy/drain path (`tasks/drain-and-reset.yml`) hard-codes four `kubernetes.core.helm` uninstalls of named istio releases (`istio-ingress`, `istio-egress`, `istiod`, `istio-base`). In practice these tasks are dead code that fails silently on every run: the `helm` binary is not installed on the master (converge logs show `Failed to find required executable "helm"` masked by `failed_when: false`), and no helm releases exist in the current scenario (Calico is installed via `kubectl apply` manifests, not helm). Meanwhile, any helm chart actually installed in the cluster (e.g. `tcharl.servicemesh` istio releases) leaves PodDisruptionBudgets behind that block `k8s_drain`.

## What Changes

- **Remove** the four hard-coded istio uninstall tasks from `tasks/drain-and-reset.yml`.
- **Add** an inline helm CLI installation on the master (`get.helm.sh` static binary → `/usr/local/bin/helm`), idempotent, version pinned in a variable, architecture derived from `ansible_arch` (`x86_64`→`amd64`, `aarch64`→`arm64`). This task fails loudly (no `failed_when: false`).
- **Add** a discovery task: `helm list -A --all -o json` (all namespaces, including non-`deployed` releases) using the cluster `kubeconfig`, registered for the next task.
- **Add** a generic uninstall task: `kubernetes.core.helm` with `release_state: absent` and `wait: false`, looping over the discovered releases (filtered to `deployed`/`failed` status), each with its own `name` and `namespace`.
- Behavior when no releases exist: the list is empty and the uninstall loop is a no-op — safe on clusters with no helm usage at all.
- The subsequent drain / node-deletion / `kubeadm reset` steps are unchanged.

## Capabilities

### New Capabilities

- `kube-drain-reset`: The Kubernetes destroy/drain path — generic helm release removal before node drain, ensuring PDB-protected workloads from any helm chart never block the drain.

### Modified Capabilities

(none)

## Impact

- `tasks/drain-and-reset.yml` — the only file modified.
- New runtime dependency: `helm` CLI binary on the master, downloaded from `get.helm.sh` at destroy time (no package repository involvement).
- No converge-path behavior change; the sweep runs exclusively in the `delete.yml` → `drain-and-reset.yml` destroy flow (`run_once` on the first master).

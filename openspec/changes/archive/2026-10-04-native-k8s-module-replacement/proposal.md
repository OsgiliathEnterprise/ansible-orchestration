# Proposal

## Why

Nine cluster operations in this role are implemented as `kubectl`/shell tasks even though the installed `kubernetes.core` v6.6.0 provides native modules for all of them — including arbitrary `kubeconfig` paths, which two task files incorrectly document as unavailable ("no native module accepts an arbitrary kubeconfig path" — verified false in `args_common.py`/`client.py`). The shell tasks carry fragile parsing (awk column indices), swallowed failures (`failed_when: false` masking real errors), and hardcoded `changed_when`. One latent bug is already visible: the coredns restart runs bare `kubectl` with no resolvable kubeconfig at that point in the flow, so it is likely a silent no-op on fresh installs.

## What Changes

- Replace 9 shell/kubectl operations across 6 task files with native `kubernetes.core` modules (`k8s_info`, `k8s`, `k8s_cluster_info`, `kubeconfig`), reusing the existing `{{ kube_config_path }}` + `context: kubernetes-admin@kubernetes` pattern already used by `persistent-volume.yml`.
- **Rollout restarts become strategic-merge annotation patches** (`kubectl.kubernetes.io/restartedAt`) with native `wait: true` — the module's `daemonset_ready`/`deployment_ready` predicates check exactly the fields `kubectl rollout status` uses.
- **Calico CA-recovery trigger becomes conditional**: the restart annotation value is a fingerprint of the current post-swap CA (`slurp` + `hash('sha256')`), so recovery fires only when the CA actually changed — making the spec's "recovery is idempotent" scenario true by construction instead of relying on unconditional churn.
- **Coredns restart becomes a hard gate** (intentional semantic change): explicit kubeconfig + context, version-tied annotation value (`calico-{{ calico_cni_version }}`), `wait: true`. Previously best-effort with all failures swallowed; now converge fails if the rollout does not complete within the timeout.
- Add a node-naming coverage assert after the calico wait so a readiness timeout names the affected node(s) (satisfies the existing "CNI not ready in time" scenario, which the current shell loop also does not satisfy).
- Lease-freshness and scheduler-readiness gates become `k8s_info` polls; post-swap connectivity verification becomes `k8s_cluster_info`; admin credential injection becomes the native `kubeconfig` module (drops `failed_when: false`/`changed_when: False` hacks); node join verification becomes a `k8s_info` poll using the worker's own `/etc/kubernetes/kubelet.conf`.
- Add variable `kubernetes_rollout_wait_timeout` (default 300) for rollout waits.
- Remove the now-false "documented exception" comments in `ipa-pki-swap.yml` and `calico-ca-recovery.yml`.

**Not changed**: `openssl verify -CAfile` chain validation in `ipa-certs.yml` (legitimate shell exception — no native module), file operations, `get_url` calicoctl download. No new dependencies: `prereq.yml` already pip-installs the `kubernetes` client on all hosts.

## Capabilities

### New Capabilities

- `kube-dns-readiness`: cluster DNS workload is restarted with an explicit admin kubeconfig after CNI installation, and converge waits for rollout completion (hard gate); restart is version-tied so re-converge at unchanged CNI version is a no-op.

### Modified Capabilities

- `ipa-pki-bootstrap`: "Pre-existing Calico/Tigera workloads trust the post-swap CA" — the rolling-restart trigger becomes conditional on the calico-node workload not yet reflecting the current post-swap CA (fingerprint-gated), so re-converge with an unchanged CA is a no-op rather than unconditional churn.

## Impact

- **Code**: `tasks/calico-ca-recovery.yml`, `tasks/ipa-pki-swap.yml`, `tasks/ipa-certs.yml`, `tasks/kube-install.yml`, `tasks/admin-user.yml`, `tasks/kube-install-join-node.yml`; new variable in role defaults/vars.
- **Behavior**: coredns restart changes from swallowed best-effort to hard gate (fresh installs will actually get the restart); calico recovery stops churning on re-converge; all other operations preserve observable behavior and failure semantics.
- **Dependencies**: none added (`kubernetes` Python client already installed via `prereq.yml` pip task on all hosts).
- **Verification**: molecule `parallels` scenario (destroy → converge → verify); second converge for idempotency spot-check of the annotation no-op behavior.

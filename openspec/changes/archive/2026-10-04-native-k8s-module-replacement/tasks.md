# Tasks

## 1. Shared variable

- [x] 1.1 Add `kubernetes_rollout_wait_timeout: 300` to `defaults/main.yml` (alongside `calico_cni_version`). Verify: key present in the file and resolvable — run a scratch play on localhost with `debug: msg="{{ kubernetes_rollout_wait_timeout }}"` importing the role's defaults, or confirm via `ansible-playbook --syntax-check` plus a grep of the new key.

## 2. calico-ca-recovery.yml (CA-fingerprint-gated restart + native wait)

- [x] 2.1 Replace the shell detection task with `kubernetes.core.k8s_info` (kind=DaemonSet, namespace=`calico-system`, name=`calico-node`, `kubeconfig: "{{ kube_config_path }}"`, `context: kubernetes-admin@kubernetes`), registered for a `when:` guard on downstream tasks. Verify: `ansible-playbook --syntax-check` passes and the task returns empty `resources` when the DaemonSet is absent (NotFound → no failure, per verified module behavior).
- [x] 2.2 Add fingerprint computation: `slurp` `/etc/kubernetes/pki/ca.crt` (`become: true`) + set_fact of `(content | b64decode) | hash('sha256')` truncated to 16 chars (e.g. fact `calico_ca_fingerprint`). Verify: scratch play on the master prints a stable 16-char hex value that is unchanged across two runs with an unchanged CA file.
- [x] 2.3 Replace the `kubectl rollout restart` + awk coverage-loop tasks with a single `kubernetes.core.k8s` task (state=present, partial spec setting only `spec.template.metadata.annotations['restartedAt'] = "ca-{{ calico_ca_fingerprint }}"`, `wait: true`, `wait_timeout: "{{ kubernetes_rollout_wait_timeout }}"`), wrapped in a `block`; add a `rescue` that runs `k8s_info` for pods (`calico-system`) and nodes, then fails with an explicit list of nodes lacking a ready `calico-node` pod (name-prefix match). Verify: syntax check passes; on the molecule converge the task reports `changed: true` after the PKI swap and `changed: false` on a second converge with unchanged CA.
- [x] 2.4 Remove the now-false "no native module accepts an arbitrary kubeconfig path" comment block from this file. Verify: no remaining reference to the exception claim (`grep -n "native module" tasks/calico-ca-recovery.yml` returns nothing).

## 3. ipa-pki-swap.yml (lease gate, scheduler gate, connectivity verification)

- [x] 3.1 Replace the lease-freshness shell task with `k8s_info` on `coordination.k8s.io/v1` Lease `kube-controller-manager` (`kube-system`, explicit kubeconfig/context), `until` age < 90 computed from `lookup('pipe', 'date +%s')` and the lease's `renewTime` via `to_datetime`/`strftime('%s')`. Verify: syntax check passes; on converge the gate polls until fresh (no `now` lookup used — verified absent in this core).
- [x] 3.2 Replace the scheduler-readiness shell task with `k8s_info` kind=Pod, namespace=`kube-system`, `label_selectors: ['component=kube-scheduler']` (plural list option name), `until` all container statuses ready. Verify: syntax check passes; converge proceeds only after the scheduler pod reports ready containers.
- [x] 3.3 Replace the `kubectl cluster-info` verification task with `kubernetes.core.k8s_cluster_info`, `until` on `.version.server` (module returns `.apis`/`.connection`/`.version` — no `.resources` key); keep the call site's existing failure semantics (`failed_when: false` if the original was best-effort). Verify: syntax check passes; converge logs the server version instead of raw stdout lines.
- [x] 3.4 Remove the now-false "documented exception" comment from this file. Verify: `grep -n "native module\|exception" tasks/ipa-pki-swap.yml` returns nothing relevant.

## 4. ipa-certs.yml (best-effort connectivity check)

- [x] 4.1 Replace the best-effort `kubectl cluster-info` task with `kubernetes.core.k8s_cluster_info` (`failed_when: false`, explicit kubeconfig/context), replacing the stdout-lines debug with a debug of `.version.server`. Verify: syntax check passes; converge shows the version debug output and does not fail when the API is briefly unavailable.

## 5. kube-install.yml (coredns restart hard gate)

- [x] 5.1 Replace the bare `kubectl rollout restart` coredns task with a `kubernetes.core.k8s` task: state=present, partial spec setting only `spec.template.metadata.annotations['restartedAt'] = "calico-{{ calico_cni_version }}"`, explicit `kubeconfig: "{{ kube_config_path }}"` + `context`, `wait: true`, `wait_timeout: "{{ kubernetes_rollout_wait_timeout }}"`; remove `failed_when: false` (deliberate hard-gate upgrade per design D11). Verify: syntax check passes; on a fresh converge the task reports `changed: true` and waits for rollout, and on a second converge at unchanged CNI version it reports `changed: false`.

## 6. admin-user.yml (native kubeconfig credential injection)

- [x] 6.1 Replace the `kubectl config set-credentials` shell task with the native `kubernetes.core.kubeconfig` module merging the admin user entry into `/etc/kubernetes/admin.conf` (cert/key by path, matching what `set-credentials` wrote); remove the `failed_when: false` + `changed_when: False` hacks. Verify: syntax check passes; after converge, `admin.conf` contains the user entry and a subsequent run reports no change (hash-idempotent).

## 7. kube-install-join-node.yml (native join verification)

- [x] 7.1 Replace the `kubectl get node` polling loop with `kubernetes.core.k8s_info` kind=Node, `name: "{{ inventory_hostname }}"`, `kubeconfig=/etc/kubernetes/kubelet.conf` (worker's own identity — no admin.conf dependency), `until resources | length > 0` with retries/delay preserving the original 40×5s timing. Verify: syntax check passes; on converge each node task succeeds only after its Node object appears, using kubelet.conf exclusively.

## 8. Integration verification (molecule)

- [x] 8.1 Run the full cycle: `uv tool run --python 3.13 --with tox tox -e destroy -- --scenario-name=parallels` then `tox -e converge-monorepo -- --scenario-name=parallels`. Verify: converge completes; calico recovery fires once after PKI swap with node-naming rescue intact (no shell kubectl tasks remain in the six files — `grep -rn "kubectl" tasks/` shows only legitimate remaining uses); coredns restart is a hard gate. **Verified (converge-7, fresh install):** PLAY RECAP failed=0 on all hosts; calico recovery fired exactly once via native module (`changed: true`, 85s wait, annotation `restartedAt: ca-cd19fc...` = CA fingerprint, final status 3/3 ready); node-naming rescue intact (rescued=0 — not needed on clean run); coredns restart fired as hard gate (`changed: true`, 45s wait, annotation `calico-v3.32.1`, 2/2 ready); no shell kubectl tasks remain in the six files.
- [x] 8.2 Run `tox -e verify-monorepo -- --scenario-name=parallels`. Verify: all testinfra tests pass against the post-converge state. **Verified (verify-5):** 63/63 passed against the fresh post-converge cluster.
- [x] 8.3 Re-run converge (second pass) for idempotency spot-checks. Verify: coredns task reports `changed: false` at unchanged CNI version; calico recovery reports `changed: false` at unchanged CA fingerprint; no workload churn observed (`kubectl get pods -n kube-system -o jsonpath` creationTimestamps unchanged). **Verified (converge-8, second pass) with one design finding:** this role's pre-existing reset-and-rebuild design re-initializes the control plane on every converge (Node objects deleted, PKI cleaned, `kubeadm init` re-run → coredns Deployment and Calico DaemonSet recreated fresh), so a full second-pass converge cannot exhibit `changed: false` for these tasks — they correctly fire against freshly-created workloads (each exactly once; no double-firing). Gate idempotency semantics verified directly instead: post-converge-8 annotation values match computed markers (`calico-node restartedAt = ca-cd19fc...` == sha256 of current `/etc/kubernetes/pki/ca.crt`; `coredns restartedAt = calico-v3.32.1` == CNI version), so a re-run against unchanged state is a no-op; all 24 pods healthy (23 Running + 1 Completed); verify-6: 63/63 passed against the post-pass-2 state.

# Design

## Context

See proposal.md for motivation. Current state: `tasks/ipa-pki-swap.yml` replaces `/etc/kubernetes/pki/ca.crt`, restarts the API server / controller-manager / scheduler static pods, and refreshes the kubelet (handler `refresh kube`). It does **not** touch data-plane workloads that were created before the swap. The `tigera-operator` (installed during `kube-install.yml`) therefore keeps its pre-swap in-cluster `ca.crt`, crash-loops on `unknown authority`, and never deploys `calico-node` to worker nodes → workers stay `NotReady`.

Constraint: the recovery must run **after** the existing kubelet refresh + cluster stabilization, so that when a fresh pod is created, kubelet serves it the post-swap CA. It runs on the master (kubectl access), same host as the rest of the swap.

## Goals / Non-Goals

**Goals:**
- Rolling-restart the pre-swap `calico-node` DaemonSet so each node re-materializes its in-cluster CA with the post-swap CA and CNI initialises.
- Gate converge completion on a Ready `calico-node` pod on every node, making the CNI end-state deterministic.

**Non-Goals:**
- No change to how certificates are generated/replaced or how control-plane static pods restart (existing behavior preserved).
- Not a general "recreate all pods in the cluster" sweep — scoped to Calico/Tigera data-plane workloads affected by the CA swap.
- Does not alter `restart-resilience`'s verify-phase kubelet-restart gate; it complements it at converge time.

## Decisions

**D1 — Placement: new included task file.** Add `tasks/calico-ca-recovery.yml`, invoked via `include_tasks` at the end of `ipa-pki-swap.yml`.
- *Why:* follows the role's modular pattern (cf. `persistent-volume.yml`, `_server-inner.yml`), isolates recovery + wait logic for clarity and independent verification, keeps `ipa-pki-swap.yml` focused on cert replacement + control-plane restart.
- *Alternative considered:* inline tasks appended to `ipa-pki-swap.yml` — smaller diff but mixes the data-plane concern into an already-long file.

**D2 — Recreation mechanism: rolling-restart the `calico-node` DaemonSet.** Run `kubectl -n calico-system rollout restart daemonset/calico-node`. Each node's pod is replaced one-at-a-time so kubelet re-materializes the post-swap in-cluster CA and CNI initialises, bringing worker nodes back to Ready.
- *Why:* directly targets the workload that must hold a fresh CA (the per-node `calico-node`); rolling keeps master's CNI up during replacement; no operator involvement.
- *Revised from:* originally we planned to `rollout restart` the `tigera-operator` and let it reconcile. During verification this proved destabilising — recreating the operator forces an image re-pull (fragile on flaky registry access → crash-loop) and, while the operator was down, dropped a worker's `calico-node`, leaving that node `NotReady`. Rolling-restarting the DaemonSet directly is less disruptive and idempotent.
- *Alternative considered:* `delete pod --all` in `calico-system` — broader but disrupts running CNI on master; per-node surgical deletion — more targeted but more complex than a rolling restart.

**D3 — Readiness gate: per-node `calico-node` only.** A single wait, using the role's existing `shell` + `retries`/`delay`/`until` idiom (matching `ipa-pki-swap.yml` lines 90–122):
- Per-node CNI: for each node, assert a Ready `calico-node` pod exists on that node; fail naming the affected node(s) if not reached within timeout. The node name is matched in any field (not a fixed column) because `get pods -o wide` appends a trailing READINESS GATES column whose presence shifts the NODE index across kubectl versions.
- *Revised from:* originally also waited for the operator to report Ready; dropped because we no longer recreate or wait on the operator — the per-node CNI gate is the sole convergence check and directly encodes the goal (every node has working CNI).

**D4 — Idempotency / no-op safety.** The recovery is gated so it does nothing when there is no Calico install (`calico-node` DaemonSet absent → skip, do not fail). When present, a post-swap rolling restart is harmless even if the pods were already healthy (brief per-pod recreation), so re-running converge never fails on this step.

## Risks / Trade-offs

- [Timing] Recreating before kubelet serves the new CA would leave the fresh pod stale → *Mitigation:* place recovery strictly after the existing kubelet refresh + `cluster_healthz`/CM-ready gates already in `ipa-pki-swap.yml`.
- [Naming drift] The node DaemonSet / namespace may differ across Calico versions (`calico-node` in `calico-system`) → *Mitigation:* detect the `calico-node` DS by name; no-op if absent (D4).
- [Timeout] First `calico-node` deploy can be slow (image pull) → *Mitigation:* reuse the role's `kubernetes_api_ready_retries` / `kubernetes_api_ready_delay` knobs for a generous, tunable wait.
- [Scope] Other pre-swap `calico-system` pods (e.g. `csi-node-driver`) may also hold stale CA → *Trade-off:* primary fix targets the `calico-node` DaemonSet (critical path for node CNI); broader recreation is optional and can be added if those pods show CA-related failures.

## Migration Plan

Additive; no data migration or API change. Deploy by re-running converge (`tox -e converge-monorepo`). Rollback = remove the `include_tasks` line from `ipa-pki-swap.yml` and delete `tasks/calico-ca-recovery.yml`. Verify via molecule verify: both nodes Ready, operator healthy, `calico-node` present on every node.

## Open Questions

- Is `csi-node-driver`'s `ContainerCreating` state CA-related or a separate (volume/scheduling) issue? Deferrable — does not change the calico-node-restart approach; confirm live during verification and broaden D2 only if it is CA-related.

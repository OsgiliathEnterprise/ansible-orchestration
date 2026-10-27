# Design

## Context

After `ipa-pki-swap.yml` replaces `/etc/kubernetes/pki/ca.crt`, control-plane
static pods restart with the new CA, but running `calico-node` pods retain
their stale in-cluster CA. Restarting the DaemonSet lets kubelet materialize
the new CA and returns worker-node CNI to Ready.

The recovery is gated by the DaemonSet lookup and a `ca-<sha256>` template
annotation. Therefore, clusters without Calico are a true no-op and a
re-converge with the same CA does not restart pods.

## Decisions

### D1 - Patch strategy and trigger atomically

The existing `kubernetes.core.k8s` task sets
`spec.updateStrategy.rollingUpdate.maxUnavailable` from
`calico_recovery_max_unavailable` in the same patch as the `restartedAt`
annotation. The default is `"100%"`; a scenario may set `"1"` for serial
recovery.

This produces one rollout and one wait. It removes the serial CNI-init chain:
parallel replacement measures roughly 45 seconds on the three-node topology,
compared with roughly 75 seconds serially. The accepted trade-off is a
10-30-second data-plane interruption on each node during a CA-triggered
restart. A measured approximately three-second old-to-new handoff confirms
that new CNI initialization does not rely on the terminated pod.

The Calico operator may later restore its preferred strategy. That is
acceptable: the role atomically reapplies its selected strategy whenever a
future CA change triggers recovery. The role does not modify the operator's
`Installation` custom resource or otherwise alter unrelated rollouts.

### D2 - Collect evidence once on timeout

The rescue block collects read-only failure evidence before failing:

1. Full Calico pod objects and all cluster nodes determine which nodes lack a
   `Ready=True` pod.
2. The `calico-node` DaemonSet supplies `metadata.generation`,
   `status.observedGeneration`, and desired/updated/ready counts. The status
   path is required; `metadata.observedGeneration` is not a valid DaemonSet
   field.
3. One namespace-wide Event list is queried and filtered in memory by
   `involvedObject.name` to identify the newest event for every non-Ready pod.
   This avoids one API request per pod.

Every optional pod, event, and status path uses a placeholder default, so
partially populated Kubernetes objects cannot turn a rollout timeout into a
template failure. `Ready` is the string `"True"` in the Kubernetes condition,
not a boolean. `lastTimestamp` remains the available event ordering field on
the supported cluster version; the runtime regression guard must cover its
sort and fallback behavior.

### D3 - Verify both strategy profiles

`molecule/parallels` verifies the default parallel strategy. A new
`molecule/parallels-sequential` scenario reuses the same topology and only
sets `calico_recovery_max_unavailable: "1"`, exercising the serial path
without topology or host-load differences. Both are run independently with
destroy between cycles. The existing `kvm` timeout override remains a
hardware-calibration decision, not a strategy change.

### D4 - Gate the cluster-wide calico wait on all nodes, not just the master

The cluster-wide `calico-ca-recovery` (a DaemonSet patch that restarts every
node's pod) is preceded only by a master-only Ready gate (`ipa-pki-swap` "wait
for master node to report Ready"). On the KVM single order-tolerant play the
master and the single worker converge **concurrently**, so the master's
cluster-wide calico wait implicitly depends on the worker's still-in-progress
convergence. The 600s budget (calibrated for CNI init only, ~30-45s) does not
cover the worker's remaining convergence, so the wait times out.

Fix: add an **all-nodes** Ready gate (cluster-wide `Node` `k8s_info`, not
master-only) **before** the cluster-wide calico patch, so that by the time the
DaemonSet is restarted every node's kubelet is already up with the post-swap CA
and the post-patch wait is bounded to CNI init (~30-45s, parallel). This keeps
the KVM `calico_recovery_max_unavailable: "100%"` parallel full-reset (the
intended CI-speed optimization) while making the wait bounded and correct.
`parallels` (sequential plays) is unaffected: the worker has already converged
before the master's play runs.

Pending confirmation: the change's rescue `fail` line distinguishes "slow CNI
init / cross-host wait" (ContainerCreating) from a genuine CNI failure
(CrashLoopBackOff / x509). The latter needs a CNI fix, not a gate.

## Non-Goals

- Managing the Calico operator or its `Installation` custom resource.
- Changing timeout budgets as a substitute for parallel recovery.
- Parallelizing unrelated role rollouts.
- Creating a new standalone OpenSpec capability; this behavior belongs to
  `ipa-pki-bootstrap`.

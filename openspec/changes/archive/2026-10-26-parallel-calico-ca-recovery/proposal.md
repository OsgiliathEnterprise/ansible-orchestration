# Proposal

## Why

The CA-fingerprint-triggered `calico-node` restart in
`tasks/calico-ca-recovery.yml` inherits the Calico operator's
`rollingUpdate.maxUnavailable: 1` default. Each replacement pod spends roughly
30-45 seconds initializing CNI before the next node can begin, so recovery
time grows with the node count against a fixed 300-second timeout. A timeout
also needs enough evidence to distinguish controller lag, CNI initialization,
and image-pull failures without manually inspecting the cluster.

## What Changes

- Add `calico_recovery_max_unavailable`, defaulting to `"100%"`, and patch it
  atomically with the CA-fingerprint `restartedAt` annotation. The default
  overlaps CNI initialization across nodes while retaining `"1"` as a
  selectable serial strategy.
- Add a `parallels-sequential` Molecule scenario that uses `"1"` on the same
  topology as `parallels`, so both strategies are verified independently.
- Make timeout failures self-diagnosing: collect Calico pods, all cluster
  nodes, DaemonSet generation/progress state, and one namespace-wide Event
  list; filter the events in memory to report the latest event for each
  non-Ready pod. All optional object paths degrade to placeholders rather than
  masking the original rollout timeout.
- Preserve existing no-op guarantees: no `calico-node` DaemonSet means no
  Kubernetes object is created, and an unchanged CA fingerprint causes no pod
  churn.
- Keep timeout budgets at 300 seconds by default and 600 seconds for the
  constrained `kvm` scenario.

## Capabilities

### Modified Capabilities

- `ipa-pki-bootstrap`:
  - Existing Calico/Tigera workloads recover with a configurable,
    CA-change-gated update strategy (parallel by default).
  - The readiness timeout reports actionable pod, node, event, and DaemonSet
    progress evidence.

## Impact

- `defaults/main.yml` and `tasks/calico-ca-recovery.yml`
- `molecule/parallels/` and new `molecule/parallels-sequential/`
- `openspec/specs/ipa-pki-bootstrap/spec.md`

During a CA-triggered parallel restart, Calico is briefly unavailable on all
nodes. This occurs only when the CA changes; the kube-apiserver static pod is
unaffected, and the measured old-to-new handoff shows that new CNI
initialization does not depend on the terminating Calico pod.

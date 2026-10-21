# Proposal

## Why

Travis CI (`kvm` scenario, single-worker topology) fails at `Calico-ca-recovery | patch calico-node template annotation to trigger rolling restart` (`tasks/calico-ca-recovery.yml:45`) with `"DaemonSet" "calico-node": Timed out waiting on resource`: the native `kubernetes.core.k8s` wait (`wait: true`, `wait_timeout: kubernetes_rollout_wait_timeout`, role default **300s**) does not complete on the constrained CI topology — 2GB/2vCPU VMs on an 8GB/2vCPU runner — while the `parallels` profile (8GB workers, local host) passes. The DS status at timeout (1/2 updated, 1/2 ready, controller status unchanged for the full 303s) shows the first node's new pod never reached Ready within the budget, so the serial rollout (`maxUnavailable: 1`, `maxSurge: 0`) never started the second node. The strict rollout-completion wait introduced by `native-k8s-module-replacement` is a true invariant that the old per-node coverage check silently masked; the KVM CI simply cannot meet 300s.

## What Changes

- The KVM scenario's converge playbook sets `kubernetes_rollout_wait_timeout` to a scenario-scoped value larger than the role default (initial value **600s**, calibrated from the observed calico wait `duration`), so the calico-node DaemonSet rollout — and the coredns rollout in `tasks/kube-install.yml` that shares the variable — can complete under CI load.
- The role default stays **300s**; `default`, `parallels`, and `default_noreset_kube` scenarios are untouched and keep the default.
- The override is a play-level var in `molecule/kvm/converge.yml` (the established home for scenario-scoped vars), with a comment recording the topology constraint and the calibration rule.
- Verification captures the calico task's measured `duration` from the Travis `master` job log on a successful KVM converge (the `kvm` scenario cannot run on the macOS host and no Linux box is available, so KVM verification is CI-only) and records the calibration evidence; a failure instead preserves the rescue's node list from the CI log as the slow-vs-stuck discriminator.

## Capabilities

### New Capabilities

(None)

### Modified Capabilities

- `kvm-scenario-topology`: gains a requirement that the KVM scenario overrides `kubernetes_rollout_wait_timeout` above the role default so workload rollout waits fit the single-worker CI topology, while non-KVM scenarios retain the role default.

## Impact

- `molecule/kvm/converge.yml` — one var added to the play `vars:` block (`kubernetes_rollout_wait_timeout`).
- Affected behavior at KVM runtime only: the calico-node rolling-restart wait (`tasks/calico-ca-recovery.yml`) and the coredns rollout wait (`tasks/kube-install.yml`) both consume the variable; worst-case converge time in CI grows by up to ~300s on failure (still within `travis_wait 70`).
- `openspec/specs/kvm-scenario-topology/spec.md` — new requirement + scenarios.
- No change to role tasks, defaults, or other scenarios; no API or dependency changes.
- Out of scope: any fix for a genuinely stuck calico pod (CNI/CA fault or OOM) — if the raised budget still fails, the captured pod state becomes the input to a follow-up change.

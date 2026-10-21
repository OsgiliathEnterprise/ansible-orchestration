# Design

## Context

See `proposal.md` for motivation. Current state that shapes the approach:

- `kubernetes_rollout_wait_timeout` is a role default (**300s**, `defaults/main.yml:41`) consumed by two wait sites: the calico-node rolling restart (`tasks/calico-ca-recovery.yml`, native `kubernetes.core.k8s` with `wait: true`) and the coredns rollout (`tasks/kube-install.yml:141`).
- `molecule/kvm/converge.yml` is a single order-tolerant play (`hosts: kube_master,kube_node`) whose `vars:` block is the established home for scenario-scoped vars (`preferred_nic`, `company_domain`, …). Play vars override role defaults.
- The CI failure evidence: DS status frozen at 1/2 updated / 1/2 ready for the full 303s wait; `maxUnavailable: 1, maxSurge: 0` makes the 2-node rollout serial, so the second node never started. The `parallels` profile (8GB workers, local host) completes the same wait comfortably.
- This host is macOS: the `kvm` scenario (libvirt) cannot run locally and no Linux box is available — KVM verification is the Travis `master` job only. The `kvm-single-node-scenario` change already cut the topology to one worker to reduce CI cost.

## Goals / Non-Goals

**Goals:**

- The KVM scenario's converge completes the calico-node rollout (and coredns rollout) under CI load, so the Travis `kvm` job passes `converge`.
- The budget stays evidence-driven: the initial value is a starting point, calibrated from the measured wait `duration` in a successful run.
- All other scenarios keep the role default; the role itself is untouched.

**Non-Goals:**

- No change to the wait mechanism: the native `kubernetes.core.k8s` `wait: true` stays (per `native-k8s-module-replacement` design D4); no re-introduction of shell polling.
- No change to the KVM platform topology (already single-worker) or to `travis_wait 70`.
- No fix for a genuinely *stuck* calico pod (CNI/CA fault, OOM): if the raised budget still fails, the captured pod state is the input to a follow-up change, not an expansion of this one.
- No change to `default`, `parallels`, or `default_noreset_kube`.

## Decisions

### D1: The override lives in `molecule/kvm/converge.yml`'s play `vars:` block

One line — `kubernetes_rollout_wait_timeout: 600` — added to the existing `vars:` block, with a comment naming the topology constraint and the calibration rule.

Alternatives considered:

- **Raise the role default (300 → 600 globally)** — rejected: penalizes the fast local scenarios with a larger failure delay, and hides the budget/topology mismatch instead of pinning it to the constrained topology.
- **`molecule.yml` env var (`provisioner.env`)** — rejected: env vars are not Ansible vars; the variable is consumed as an Ansible var, so an env var would require a `lookup('env', …)` indirection the scenario does not use anywhere.
- **Per-scenario defaults file** — rejected: molecule has no per-scenario role-defaults mechanism; the play `vars:` block is the existing scenario-var channel.

### D2: Initial value 600s, calibrated from the measured duration

The failure window shows the first node's new pod was not Ready for the entire 300s, and the serial 2-node rollout then never started the second node — so the true requirement is at least "one slow node phase + a second node phase". 600s gives 2× headroom over the observed window. The k8s task reports its actual `duration` in the result (the failure log shows `duration: 303`); on a successful KVM converge the measured calico wait duration is recorded and the budget is kept at ≥2× the observed worst case. If a measured duration exceeds 50% of the budget, the value is raised accordingly (still bounded by the `travis_wait 70` job budget).

### D3: The coredns wait inherits the override deliberately

`tasks/kube-install.yml:141` (coredns rollout) consumes the same variable. The KVM override extends that wait too — intentional, since it is the same constrained topology (a coredns rollout on the same 2GB nodes under the same load profile). No per-site variable split is introduced: one budget, one topology.

### D4: Verification is CI-gated; local gates are regression-only

`kvm` (libvirt) cannot run on this macOS host and no Linux box is available — KVM verification is not run locally at all. Local gates: `tox -e lint` (yamllint + ansible-lint), `molecule syntax` for the kvm scenario, and the full `parallels` cycle (destroy → converge-monorepo → verify-monorepo) as the no-regression proof that the default-300 path is untouched. KVM verification: the Travis `master` job (`tox -e test-exec -- --scenario-name kvm`) on push only.

### D5: Slow-vs-stuck discriminator is the captured evidence, not a code path

On a successful KVM converge: record the calico task's `duration` from the Travis log (calibration evidence for D2). On a failure: the existing rescue (`tasks/calico-ca-recovery.yml:64-110`) names the node(s) lacking a Ready calico pod, and that CI-log output is the slow-vs-stuck evidence recorded in this change; if a pod is stuck (mechanism fault — CA/CNI or memory), the pod-state inspection (`containerStatuses.waiting.reason`, `dmesg` OOM, `/var/log/calico/cni/`) becomes the input to a follow-up change, only if live VM access becomes available. A stuck pod is a different change.

## Risks / Trade-offs

- [The pod is genuinely stuck and no budget helps] → The calibration step (D5) captures pod state on failure; the fork into a follow-up change is explicit in the tasks. The rescue already exists, so no new diagnostic code is needed.
- [CI job budget: up to ~300s extra worst-case on failure, inside `travis_wait 70`] → The single-worker topology (archived `kvm-single-node-scenario`) already cut converge cost; if the job budget is exceeded, splitting the Travis job (`molecule test --test-sequence`) is the documented follow-up from that change — no scope impact here.
- [600s is still too small / too large] → D2's calibration rule is evidence-driven (measured `duration`), so the value converges to the topology's actual requirement rather than guesswork.
- [Variable-name drift between role default and scenario override] → Both reference the same variable by name; the spec scenarios pin the resolved value per scenario, and `tox -e lint` gates the touched file.

## Migration Plan

Single-commit change, no runtime impact until the next KVM CI run:

1. Lint gate: `tox -e lint`.
2. Syntax gate: `molecule syntax --scenario-name kvm`.
3. No-regression proof (macOS): full `parallels` cycle — destroy → converge-monorepo → verify-monorepo — confirming the role default (300) path is unchanged and green.
4. KVM verification: Travis `master` job on push (`tox -e test-exec -- --scenario-name kvm`) — not runnable locally (macOS host, no Linux box); the task list deliberately has no local KVM verification.
5. Calibration: record the calico task `duration` from the successful converge log; adjust the value per D2 only if the measured duration exceeds 50% of the budget.
6. Rollback: delete the one var line from `molecule/kvm/converge.yml` — the role default (300) resumes; independent of any other in-flight change.

## Open Questions

None blocking. The initial 600s value is a design decision with a calibration escape hatch (D2), not a deferrable unknown; the slow-vs-stuck fork (D5) is a verification outcome, not a scope decision.

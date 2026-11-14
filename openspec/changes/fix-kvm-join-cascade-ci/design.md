# Design

## Context

See `proposal.md — Why` for the incident and suspects. Constraints that shape the approach:

- The failing environment is the **kvm scenario on Travis (Linux)**; per the monorepo host-OS rule this control machine (macOS) can only run `parallels`/`parallels-sequential`. The root cause cannot be reproduced locally; evidence came from the Travis log, a same-commit re-run, and a local parallels run of the same commit for scenario-independence.
- `molecule/kvm/converge.yml` is a **single play over `kube_master,kube_node` with no `serial:`** — master and node run **concurrently**; cross-host ordering is delegated entirely to the in-role readiness gates (per the play's own comment). The earlier "serial execution makes the first `fatal:` the discriminator" assumption in this design was wrong and is superseded by `evidence.md`: the master stayed alive ~20 min past the node's gate timeout, so the node's failure is the *primary* one and the master's late `failed=1` is the cascade.
- Root cause (closed, `evidence.md`): the node's profile gate (`kube-install-join-node.yml:39`) waits on the generic `orchestration_readiness_*` budget (40×5 s ≈ 271 s wall) while the master's path to profile creation (`tasks/certs/ipa-kubernetes-ca.yml:178`) takes longer than that on the constrained CI runner — a race with a stably-negative margin (two byte-identical runs), surfaced by (not introduced by) `c5694a6`, which added time to the master's pre-profile path. The gate predates `c5694a6`.
- The Travis log names the dying task directly: `Kube-install-join | wait for kubernetesNodes profile to exist in FreeIPA` (line ~39), 40 identical attempts, `stdout: "0"` — the profile was genuinely absent for the whole window (gate mechanics and ticketing both exonerated in `evidence.md`). The join never reached its config stages (kubelet crash-loop over the absent `config.yaml` is residue from the tcharl.kubernetes role's disabled join attempt, not a causal signal).
- The suspect commit `c5694a6` (self-signed kube CA retirement) touched exactly the CA-retirement path and added the second delegated CA fetch. Prior archived changes validated on parallels only.

## Goals / Non-Goals

**Goals:**
- ~~Deterministic diagnosis of the kvm failure~~ — **achieved**: two byte-identical re-runs + code/timing proof closed the root cause as a node profile-gate race (`evidence.md`); the fix is the minimal one implied by that evidence.
- Join-phase hardening sufficient that the *next* failure self-reports its phase, dependency, and journal window — in any scenario, without CI-specific config.
- Bounded-retry resilience for the two delegated CA fetches.

**Non-Goals:**
- Play splitting / per-play `any_errors_fatal` restructure (Phase 1 `join-pipeline-failure-isolation`) — refactoring on a red baseline destroys fix attribution.
- Per-gate budget split of `kubernetes_api_ready_retries` (Phase 1).
- `kubeadm-config` ConfigMap drift (Phase 2), renewal telemetry (Phase 3), workload smoke tests (Phase 4).

## Decisions

**D1 — Evidence gate before any root-cause code change.** Executed. The gate collected: (a) the node's verbatim `fatal:` from the fetched Travis log (done), (b) same-commit re-run verdict — two byte-identical node failures → deterministic, not a flake (done), (c) local parallels converge on the same commit (pending, tasks.md 1.3). The master's first `fatal:` never appeared in the fetched excerpts (log lost), but the bucket decision closed without it: the node-side race is proven by code + PIPELINE timing (31.5 min converge vs the node's 271 s gate window, master alive ~20 min past the node's death). Rationale held: three candidate buckets (master cert chain / node upstream starvation / flake) implied different fixes, and coding blind risked a "raise the timeout until Travis passes" patch — the anti-pattern the plan doc bans. The evidence instead measured the race and justified a named budget.

**D2 — Diagnostics live in Ansible's rescue path, not Travis config.** All diagnostic capture runs inside the existing `rescue:` block of `kube-install-join-node.yml`: every capture task carries `failed_when: false` so the original failure message is preserved. Rationale: scenario-agnostic (works on Travis kvm, local parallels, any future backend), testable locally, no `after_failure` vagrant-id fragility. The rescue prints: `ansible_failed_task.name` (phase — task names already carry the `Kube-install-join |` prefix), `ansible_failed_result` key fields, `journalctl -u kubelet --since <block-start>` (captured at block entry via a node-local `date -Is` fact so the journalctl clock and the anchor share the host clock), `crictl pods`/`crictl ps`, `ipa-getcert list`, keytab presence checks, and a final attribution line: when the failed task is an API/profile/CA gate, the message names the upstream dependency (master `tasks/certs/ipa-certs.yml` completion, idm CA availability). Alternative considered: molecule `after_failure`/Travis hook — rejected for the reasons above.

**D3 — Retry the fetches, but fail persistents by name.** Both `ipa ca-show` tasks get `retries: 6` / `delay: 10` with the `until` condition also requiring the output file to be non-empty and contain `BEGIN CERTIFICATE`; a post-fetch task fails with a message naming the CA and the IPA host if the check never passes. Slurps stay unretried (they read an idm-local file just written by a verified fetch). Rationale: distinguishes transient IPA API/DS storms (retryable, matches the profile gate's discipline) from a genuinely missing CA (must fail fast and named, never be retried into a late timeout).

**D4 — Root-cause fix is bucket-selected from evidence; collapsed after the evidence gate.** The three candidate buckets were collapsed to one (see `evidence.md` Verdicts): node profile-gate starvation on the constrained CI runner. The executed fix (tasks 2.1–2.2) gives the profile gate its own join-scale budget (dedicated vars, ~20 min ceiling, ≥ 2× measured CI worst case) and a named-fail rescue branch that captures upstream evidence (`ipa certprofile-find` output) instead of a kubelet journal tail. Struck with notes: the "master cert-chain task" bucket (master alive ~20 min past node death → its failure is consequence, not cause) and the standalone "CA #2 fetch contention" bucket (same race class, but behind the profile gate; its hardening remains as unconditional §3.1). No `tasks/certs/` change is in scope for this fix; if future evidence names `tcharl.freeipa_server`/`tcharl.kubernetes`, raise an openspec change there (monorepo rule 4) instead of editing.

## Risks / Trade-offs

- [Retries mask a genuinely missing CA] → validity check + named fail after budget (D3), spec scenario "Missing CA fails with a named diagnosis".
- [A rescue diagnostic task throws and replaces the original error] → every capture task `failed_when: false`; the `fail:` msg is assembled first and printed last.
- [Diagnosis stalls waiting for the Travis log] → the same-commit re-run and local parallels run are independently actionable; the evidence gate lists all three sources and proceeds on whichever arrives.
- [Hardening tasks churn while the root-cause fix is unknown] → hardening is confined to the node's own rescue path and two fetch tasks; it cannot affect master-side behavior, so it cannot mask the root cause.
- [Parallels-local green diverges from kvm (2 GB vs 5–8 GB VMs, libvirt vs parallels)] → treat a parallels green + kvm red as a kvm-specific resource signal (gate budgets on constrained runners), recorded in the flake ledger rather than "fix"ed by magic constants.

## Migration Plan

Forward-only task-file changes; no state or interface migration. Rollback = revert the change's commits. The evidence gate is documentation-level and cannot break CI.

## Open Questions

- Whether the master's own gates also need artifact capture — deferred: the master's first `fatal:` was never fetched, and master-side failure isolation is exactly what the Phase 1 change (`join-pipeline-failure-isolation`) restructures. This change stays scoped to the node's join path.

# Tasks

## 1. Implement the escalation restart

- [x] 1.1 In `tasks/calico-ca-recovery.yml`, after the "name calico-node pods
  stuck not-Ready" task, add discovery tasks (`kubernetes.core.k8s_info`,
  `namespace: calico-system`, label selectors `k8s-app=calico-typha` and
  `k8s-app=calico-kube-controllers`, registered as `calico_typha_pods` /
  `calico_controllers_pods`) gated on `calico_rollout_pods.failed |
  default(false)` and `calico_recovery_restart_typha | bool`. Verify: syntax
  check passes; static gate reports zero findings (registers consumed).
- [x] 1.2 Add the two delete loops (`kubernetes.core.k8s`, `state: absent`,
  `wait: false`, loop over discovered pod names, same `when:` guard as 1.1)
  BEFORE the existing stuck-calico-node-pod deletion task; keep the stuck-pod
  deletion guard as-is. Verify: converge on the green path deletes no typha pod
  (grep the converge log — the escalation tasks report `skipping`).
- [x] 1.3 Add a `set_fact` recording `calico_recovery_escalation`
  (`typha-restart` when the restart loops ran, `pod-delete` when only stuck-pod
  deletion ran) and interpolate `escalation: {{ calico_recovery_escalation |
  default('none') }}` into the final fail message. Verify: message renders in
  the fault-injection drill (4.2) and static gate passes.
- [x] 1.4 In `defaults/main.yml`, add `calico_recovery_restart_typha: true`
  with a comment naming the stale-typha confd-starvation flake it recovers
  from. Verify: `ansible-playbook --syntax-check` + role default documented.

## 2. Static verification

- [x] 2.1 Run the committed static gate and the playbook syntax check:
  `.tox/converge-monorepo/bin/python tests/static_gate.py` → zero findings
  (no orphaned files, no unused registers);
  `ANSIBLE_ROLES_PATH=... .tox/lint/bin/ansible-playbook -i localhost,
  molecule/default/converge.yml --syntax-check` → OK.

## 3. Green-path converge (parallels)

- [x] 3.1 Full cycle: `tox -e destroy -- --scenario-name=parallels` →
  `converge-monorepo` → `verify-monorepo` → 71/71 tests pass; converge log shows
  the calico recovery ran its trigger + poll phase 1 green and the new
  discovery/delete tasks were skipped (no typha churn on a healthy cluster).
  DONE: converge EXIT 0 (`converge-drill.log`); verify 71/71 (`verify-drill.log`,
  EXIT 0). The stale-typha flake occurred LIVE on this converge (node2
  calico-node stuck 0/1 after phase 1): escalation discovered + deleted
  typha×2 + kube-controllers (all changed), fact `calico_recovery_escalation:
  typha-restart`, phase 2 Ready after 5 attempts (~50 s) — the new path
  self-healed the real flake with no manual unlock.

## 4. Fault-injection drill (escalation path)

- [x] 4.1 On a converged parallels cluster, reproduce the wedge deterministically
  (frozen typha replicas + fresh calico-node pods, see design.md "Drill
  recipe"), then re-run only the recovery through the ad-hoc harness
  (`drill/drill-calico-recovery.yml` includes the REAL task file against the
  live master; `drill/inventory.ini` points at the parallels VMs — same auth
  molecule uses, no new credentials). Verify: phase 1 times out and the
  escalation is reached. DONE: `drill-B3b.log` — phase 1 exhausted after 10
  retries (~100 s) with all three calico-node pods 0/1 (BIRD socket refused).
  NOTE: the original "re-run converge to trigger it" recipe was replaced by the
  harness (deterministic minutes-vs-hours); iptables block of 5473 from the
  pod CIDR proved ineffective (calico-node is hostNetwork — see design.md).
- [x] 4.2 With the wedge active, run the recovery and capture the log: the
  escalation deletes typha + kube-controllers pods, phase 2 recovers all
  calico-node pods Ready, the run exits green, and the report names
  `escalation: typha-restart`. Verify: drill log + `sudo kubectl get pods -n
  calico-system -o wide`. DONE: `drill-B3b.log` — frozen typha×2 +
  kube-controllers deleted (changed), phase 2 Ready after 5 attempts (~50 s),
  EXIT 0, cluster green afterwards (typha lv4bv/lzfrw 1/1, nodes Ready).
  Live-converge evidence in 3.1 corroborates the same shape on the real flake.
- [x] 4.3 Opt-out check: `calico_recovery_restart_typha: false` (`-e
  drill_restart_typha=false`), re-run the drill: escalation deletes only stuck
  pods and the run fails with `escalation: pod-delete` in the evidence message.
  Restore `true` afterwards. Verify: drill log shows the discovery and
  control-plane-restart tasks skipped. DONE: `drill-B2b.log` — the three
  control-plane tasks `skipping`, no typha churn, EXIT 2, fail message renders
  `phase: rollout, escalation: pod-delete` with per-pod BIRD evidence.

## 5. Docs sync

- [x] 5.1 Update the header comment of `tasks/calico-ca-recovery.yml` to
  describe the two-stage escalation; check the role AGENTS.md L3 graph line for
  `calico-ca-recovery.yml` remains accurate (no new include files expected). If
  platform docs under `src/site/asciidoc` describe the recovery escalation, run
  `/update-platform-docs`; otherwise note no doc change needed. Verify: diff
  reviewed. DONE: header comment extended; AGENTS.md L3 line verified accurate
  (no new includes); `reference-variables.adoc` auto-block regenerated with
  `calico_recovery_restart_typha`; `./mvnw site` EXIT 0. No prose doc describes
  the escalation depth — no further doc change needed.

## Workflow follow-up

- Archive the change with the openspec archive workflow after 3.1 and 4.2 are
  green; sync the delta into `openspec/specs/ipa-pki-bootstrap/spec.md`.
- Commit alongside the pending ticket-dedup-hygiene commit set (user's call on
  commit granularity).

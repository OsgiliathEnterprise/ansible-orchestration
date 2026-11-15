# Tasks

## 1. Evidence gate (blocks root-cause fix, not hardening)

- [x] 1.1 (Non-blocking, confirmation only) Obtain the **first `fatal:` block** of the master's Travis kvm log if a future run yields it; it names the exact late-death gate (calico Ready vs `kubectl get nodes`). **The bucket decision no longer depends on it** — root cause was closed by code + PIPELINE timing (see `evidence.md` Verdicts). Node's fatal is recorded; master's first fatal is absent from the lost log excerpts. **OBTAINED via build #107 (commit `f1ff4f5`, join fix deployed): master's first fatal is `tasks/kube-install.yml:141` "Kube-install | Restarts coredns after calico installation" — `kubernetes.core.k8s` (`wait: true`) received `504 Gateway Timeout` ("request did not complete within the allotted timeout") from the just-initialized API server under calico bring-up load, 21:59 GMT. The master chain died there, minutes before `kubernetesNodes` profile creation → node gate starved → node named fail + rescue fired exactly as designed. Verbatim fatal + timeline in `evidence.md` (#107 post-mortem). This opened the fourth bucket — master-bringup API-call load fragility — fixed by 2.5.**
- [x] 1.2 Re-run the same commit on Travis and record the verdict (flake vs deterministic) in `evidence.md`. Verification: re-run job URL + outcome recorded. **Done: two runs, byte-identical node failure → deterministic, not a flake** (see `evidence.md`).
- [x] 1.3 Run the local `parallels` converge on the same commit (`tox -e converge-monorepo -- --scenario-name=parallels`, then `verify-monorepo`) and record whether it reproduces. Verification: outcome recorded in `evidence.md` with the scenario verdict (scenario-independent vs kvm-specific). **Done: parallels does NOT reproduce — cold protocol green on the fix commit (task 4.1, verify 74/74). Verdict: kvm/CI-runner-specific resource timing (the 8 GB/2 vCPU runner stretches master bring-up so the coredns call lands in the API server's 504-prone window and the profile appears beyond the node's old 271 s budget), not scenario-independent logic. Recorded in `evidence.md`.**

## 2. Root-cause fix (confirmed bucket: node profile-gate starvation on the constrained CI runner)

`evidence.md` collapsed the three candidate buckets to gate starvation: the profile
genuinely did not exist during the node's 271 s window while the master stayed alive
~20 min longer. Execute 2.1–2.2 and 2.5 (added after build #107); 2.3–2.4 are the struck buckets.

- [x] 2.1 Give the profile gate its own join-scale budget. New defaults
      `kube_join_profile_ready_retries: 120` / `kube_join_profile_ready_delay: 10`
      (~20 min ceiling, ≥ 2× the measured CI worst case), consumed by
      `Kube-install-join | wait for kubernetesNodes profile to exist in FreeIPA`
      (`tasks/kube-install-join-node.yml:39`) instead of the generic
      `orchestration_readiness_retries/delay` pair, which stays for the other gates.
      Record the measured pace (node window 271 s vs master reaching
      `tasks/certs/ipa-kubernetes-ca.yml:178` beyond it on the 8 GB/2 vCPU runner) in the
      commit message. Verification: kvm re-run passes the profile gate with headroom;
      local scenarios unchanged (budget is a ceiling — passes as early as the profile appears).
      **Implemented; budget override (2×2 s) exercised in the 2.2 negative test — the gate
      loop honours the new vars. kvm-headroom confirmation folds into 4.2.**
- [x] 2.2 Named-fail + upstream evidence on gate timeout (design D2 applied to this gate,
      as the upstream-evidence branch of the 3.3 phase-aware rescue): when the failed task
      is one of the upstream gates (profile / CA-content / API), the rescue captures
      `ipa certprofile-find` output from idm (`failed_when: false`) and fails with a message
      naming the missing signal (`kubernetesNodes` profile) and its master-side producer
      (`tasks/certs/ipa-kubernetes-ca.yml`), instead of dumping the journal of a kubelet that
      never started. Verification: scratch-branch negative test — point the gate at a
      nonexistent profile name and confirm the rescue output names the profile and the
      producer task, with no generic "kubelet not active".
      **PASSED 2026-11-14 (parallels re-converge with gate grepping
      `kubernetesNodesZZZ` + `-- -e` budget 2×2 s): rescue printed
      `failed_task=... wait for kubernetesNodes profile to exist in FreeIPA`, live
      `certprofile-find` inventory (8 profiles, real `kubernetesNodes` present), named fail
      attributing to `tasks/certs/ipa-kubernetes-ca.yml`. Transcript in `evidence.md`.**
- [ ] 2.3 STRUCK — "master cert-chain task" bucket (as scoped to `c5694a6`'s additions): all `c5694a6` additions before profile creation are non-fatal by construction, and in #106 the master ran ~20 min past the node's death. **Amended after #107: a master-chain task did die first after all — `tasks/kube-install.yml:141` coredns restart, a pre-existing task, killed by a transient 504 under calico bring-up load. That is the fourth bucket, handled as 2.5; the strike here stands only for `c5694a6`'s cert-retirement additions.**
- [ ] 2.4 STRUCK — "CA #2 fetch contention" bucket: the un-retried `kubeclusteradm` fetches (`:76–91`) are the same race class but sit behind the profile gate, which now carries
      the correct budget; their hardening stays as unconditional §3.1.
- [x] 2.5 Harden the master's bring-up k8s-API calls against transient 5xx (fourth bucket,
      opened by build #107): the coredns restart (`tasks/kube-install.yml:141`) ran as a single
      `kubernetes.core.k8s` call with `wait: true`, so one 504 from the just-initialized API
      server (observed at 21:59 GMT under calico bring-up load) aborted the master chain before
      profile creation and starved the node gate — the join fix's budget then waited the full
      ~20 min and produced the designed named fail + rescue, but the run still failed.
      Fix: split into (a) idempotent patch apply with `wait: false` + `until: ... is succeeded`
      (6×10 s, `failed_when: false`) + named fail carrying the last API error, and (b) rollout
      wait via `kubernetes.core.k8s_info` poll gated on `observedGeneration >= generation` and
      `readyReplicas >= replicas` (24×20 s, `failed_when: false`) + named fail with upstream
      attribution. The apply is idempotent (constant `restartedAt` value), so retries are safe;
      the wait budget is deliberately kept inside the node join gate's ~20 min ceiling so the
      master can never starve the gate behind this wait. Verification: structural guard
      `test_coredns_restart_is_load_tolerant` (`molecule/default/tests/test_master.py`) pins
      `wait: false`, `until`/`retries`/`failed_when: false`, `observedGeneration`, `readyReplicas`
      and both named-fail strings, and fails on a revert to the bare `wait: true` form
      (positive + negative proven locally); warm re-converge on the converged parallels cluster
      must run the task as a green no-op (folded into the 4.1-protocol regression before the CI
      push); CI confirmation folds into 4.2. **Implemented 2026-11-14; guard PASSED both
      directions. Warm regression PASSED 2026-11-15: reconverge on the converged parallels
      cluster green (`failed=0 rescued=0` all hosts, 572 s — the named-fail tasks after both
      loops would set `failed=1` on exhaustion, so the green RECAP proves apply + rollout
      poll both succeeded), `verify-monorepo` 75/75 (74 + the new static guard) in 37.6 s.**

## 3. Join hardening (unconditional)

- [x] 3.1 In `tasks/kube-install-join-node.yml`, add `retries`/`delay` to both `ipa ca-show` fetch tasks (lines ~55 and ~76) with an `until` condition also requiring the output file to exist, be non-empty, and contain `BEGIN CERTIFICATE`; add a post-fetch `fail` naming the CA and the IPA host if the condition never holds. Verification: manual negative test — temporarily point one fetch at a nonexistent CA name and confirm the failure message names the CA without a late join timeout. **Implemented (retries 5×5 s + PEM-header validation + named `CA_FETCH_TIMEOUT` fail on both fetches). Found-and-fixed during this task: `until`+`retries` without `failed_when: false` self-fails on exhaustion, which made the named fail tasks dead code — both fetches now carry `failed_when: false` so the named fail owns the diagnosis. PASSED 2026-11-14 (parallels re-converge, first fetch mutated to `kubernetes-caZZZ`): profile gate passed (name restored), fetch exhausted 5×5 s, rescue printed the live `certprofile-find` inventory (8 profiles — proving profile existed while CA missing), and the final fail named `CA_FETCH_TIMEOUT: CA 'kubernetes-ca' never materialised as valid PEM … Last ipa output: ipa: ERROR: kubernetes-caZZZ: Certificate Authority not found`. No late join timeout. Transcript in `evidence.md`.**
- [x] 3.2 At the top of the join block, capture `kube_join_started_at` via a node-local `date -Is` fact. Verification: fact appears in the block's debug output. **Confirmed in the Phase-A rescue output: `join_started=2026-11-14T12:49:54-06:00`.**
- [x] 3.3 Rewrite the join block `rescue:` per design D2: print the failing task name (`ansible_failed_task.name`), the original failure message, and `journalctl -u kubelet --since {{ kube_join_started_at }}`, `crictl pods -a`, `crictl ps -a`, `ipa-getcert list`, and keytab presence checks — every capture task `failed_when: false` so the original error is never masked. Verification: temporarily insert a deliberate failing task mid-block on a scratch branch and confirm the rescue output names the phase and includes all captures. **PASSED via the 2.2 negative test (gate failure is a mid-block failure): all captures present — windowed kubelet tail, crictl, ipa-getcert, artifact stat, certprofile inventory, named diagnosis. Follow-up fix from the transcript: `crictl pods -a` is not a valid flag (usage noise instead of state) → now `crictl pods`.**
- [x] 3.4 Add the upstream-dependency attribution line to the rescue output: name `tasks/certs/ipa-certs.yml` (master) and idm CA availability as the dependencies for API/profile/CA-gate failures, replacing the bare "Check kubelet logs above." Verification: grep the rescue output from 3.3's scratch run for the attribution text. **Confirmed: `Upstream dependencies for profile/CA/API gate failures: master-side certificate provisioning — tasks/certs/ipa-certs.yml, with the 'kubernetesNodes' profile created in tasks/certs/ipa-kubernetes-ca.yml — and idm CA availability`.**

## 4. Verification

- [x] 4.1 Full local cycle on the host-OS-matched scenario: `destroy → converge-monorepo → verify-monorepo` (parallels) plus a reconverge for idempotence. Verification: verify green (all nodes Ready, per-pod evidence, PV mounts) and reconverge reports no unexpected changes. **PASSED 2026-11-14 — both the warm run (converge 664 s + verify 74/74) and the formal cold-path protocol `destroy → converge (1850 s, fresh VMs + prepare) → verify (74/74) → reconverge (642 s, failed=0, rescued=0) → re-verify (74/74)` green end to end; PLAY RECAPs and verdicts in `evidence.md`. Reconverge `changed` residue is the pre-existing containerd-restart → kubelet-restart-handler chain only; the join path itself reported zero changes.**
- [ ] 4.2 Push for Travis kvm and confirm **two consecutive green kvm runs** on the fixed commit (this change's exit criterion). Verification: two green job URLs recorded in `evidence.md`. **Status: build #107 (`f1ff4f5`, job 641604072) FAILED at the coredns 504 (see 2.5 + `evidence.md` #107 post-mortem) — the join fix itself behaved exactly as designed. Coredns hardening shipped in `d869e70` (pushed to `parallel` and fast-forwarded to `master` 2026-11-15); build #108 (`d869e709`, job 641604415) started 23:09Z on master. Two consecutive greens must be on the hardened commit — #108 is run #1; on green, same-commit restart gives run #2.**
- [x] 4.3 Structural test in `molecule/default/tests/test_node.py`: assert the join rescue references `kube_join_started_at`, `journalctl --since`, `crictl`, `ipa-getcert`, and the upstream attribution string. Verification: test passes locally (4.1) and fails if the rescue is reverted. **PASSED 2026-11-14 in the 74-test verify run (`test_join_rescue_carries_phase_diagnostics`); kvm symlink set covers `test_node.py` so the guard runs on CI too.**

## Workflow follow-up

- Archive this change only after 4.2 (two consecutive Travis kvm greens) — `openspec archive fix-kvm-join-cascade-ci`.
- If §1 evidence changes the plan's Phase 1/2 assumptions (e.g. root cause is the kubeadm-config drift of Phase 2, not the join pipeline), update `docs/ca-powered-kubernetes-plan.md` sequencing before starting the next phase's change.

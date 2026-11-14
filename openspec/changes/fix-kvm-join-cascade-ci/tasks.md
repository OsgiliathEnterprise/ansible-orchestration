# Tasks

## 1. Evidence gate (blocks root-cause fix, not hardening)

- [ ] 1.1 (Non-blocking, confirmation only) Obtain the **first `fatal:` block** of the master's Travis kvm log if a future run yields it; it names the exact late-death gate (calico Ready vs `kubectl get nodes`). **The bucket decision no longer depends on it** — root cause was closed by code + PIPELINE timing (see `evidence.md` Verdicts). Node's fatal is recorded; master's first fatal is absent from the lost log excerpts.
- [x] 1.2 Re-run the same commit on Travis and record the verdict (flake vs deterministic) in `evidence.md`. Verification: re-run job URL + outcome recorded. **Done: two runs, byte-identical node failure → deterministic, not a flake** (see `evidence.md`).
- [ ] 1.3 Run the local `parallels` converge on the same commit (`tox -e converge-monorepo -- --scenario-name=parallels`, then `verify-monorepo`) and record whether it reproduces. Verification: outcome recorded in `evidence.md` with the scenario verdict (scenario-independent vs kvm-specific).

## 2. Root-cause fix (confirmed bucket: node profile-gate starvation on the constrained CI runner)

`evidence.md` collapsed the three candidate buckets to gate starvation: the profile
genuinely did not exist during the node's 271 s window while the master stayed alive
~20 min longer. Execute only 2.1–2.2; 2.3–2.4 are the struck buckets.

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
- [ ] 2.3 STRUCK — "master cert-chain task" bucket: all `c5694a6` additions before profile
      creation are non-fatal by construction, and the master ran ~20 min past the node's
      death; its `failed=1` is the consequence of the worker never joining (calico Ready
      gate / `admin-user.yml:231`), not the cause.
- [ ] 2.4 STRUCK — "CA #2 fetch contention" bucket: the un-retried `kubeclusteradm` fetches
      (`:76–91`) are the same race class but sit behind the profile gate, which now carries
      the correct budget; their hardening stays as unconditional §3.1.

## 3. Join hardening (unconditional)

- [x] 3.1 In `tasks/kube-install-join-node.yml`, add `retries`/`delay` to both `ipa ca-show` fetch tasks (lines ~55 and ~76) with an `until` condition also requiring the output file to exist, be non-empty, and contain `BEGIN CERTIFICATE`; add a post-fetch `fail` naming the CA and the IPA host if the condition never holds. Verification: manual negative test — temporarily point one fetch at a nonexistent CA name and confirm the failure message names the CA without a late join timeout. **Implemented (retries 5×5 s + PEM-header validation + named `CA_FETCH_TIMEOUT` fail on both fetches). Found-and-fixed during this task: `until`+`retries` without `failed_when: false` self-fails on exhaustion, which made the named fail tasks dead code — both fetches now carry `failed_when: false` so the named fail owns the diagnosis. PASSED 2026-11-14 (parallels re-converge, first fetch mutated to `kubernetes-caZZZ`): profile gate passed (name restored), fetch exhausted 5×5 s, rescue printed the live `certprofile-find` inventory (8 profiles — proving profile existed while CA missing), and the final fail named `CA_FETCH_TIMEOUT: CA 'kubernetes-ca' never materialised as valid PEM … Last ipa output: ipa: ERROR: kubernetes-caZZZ: Certificate Authority not found`. No late join timeout. Transcript in `evidence.md`.**
- [x] 3.2 At the top of the join block, capture `kube_join_started_at` via a node-local `date -Is` fact. Verification: fact appears in the block's debug output. **Confirmed in the Phase-A rescue output: `join_started=2026-11-14T12:49:54-06:00`.**
- [x] 3.3 Rewrite the join block `rescue:` per design D2: print the failing task name (`ansible_failed_task.name`), the original failure message, and `journalctl -u kubelet --since {{ kube_join_started_at }}`, `crictl pods -a`, `crictl ps -a`, `ipa-getcert list`, and keytab presence checks — every capture task `failed_when: false` so the original error is never masked. Verification: temporarily insert a deliberate failing task mid-block on a scratch branch and confirm the rescue output names the phase and includes all captures. **PASSED via the 2.2 negative test (gate failure is a mid-block failure): all captures present — windowed kubelet tail, crictl, ipa-getcert, artifact stat, certprofile inventory, named diagnosis. Follow-up fix from the transcript: `crictl pods -a` is not a valid flag (usage noise instead of state) → now `crictl pods`.**
- [x] 3.4 Add the upstream-dependency attribution line to the rescue output: name `tasks/certs/ipa-certs.yml` (master) and idm CA availability as the dependencies for API/profile/CA-gate failures, replacing the bare "Check kubelet logs above." Verification: grep the rescue output from 3.3's scratch run for the attribution text. **Confirmed: `Upstream dependencies for profile/CA/API gate failures: master-side certificate provisioning — tasks/certs/ipa-certs.yml, with the 'kubernetesNodes' profile created in tasks/certs/ipa-kubernetes-ca.yml — and idm CA availability`.**

## 4. Verification

- [x] 4.1 Full local cycle on the host-OS-matched scenario: `destroy → converge-monorepo → verify-monorepo` (parallels) plus a reconverge for idempotence. Verification: verify green (all nodes Ready, per-pod evidence, PV mounts) and reconverge reports no unexpected changes. **PASSED 2026-11-14 — both the warm run (converge 664 s + verify 74/74) and the formal cold-path protocol `destroy → converge (1850 s, fresh VMs + prepare) → verify (74/74) → reconverge (642 s, failed=0, rescued=0) → re-verify (74/74)` green end to end; PLAY RECAPs and verdicts in `evidence.md`. Reconverge `changed` residue is the pre-existing containerd-restart → kubelet-restart-handler chain only; the join path itself reported zero changes.**
- [ ] 4.2 Push for Travis kvm and confirm **two consecutive green kvm runs** on the fixed commit (this change's exit criterion). Verification: two green job URLs recorded in `evidence.md`.
- [x] 4.3 Structural test in `molecule/default/tests/test_node.py`: assert the join rescue references `kube_join_started_at`, `journalctl --since`, `crictl`, `ipa-getcert`, and the upstream attribution string. Verification: test passes locally (4.1) and fails if the rescue is reverted. **PASSED 2026-11-14 in the 74-test verify run (`test_join_rescue_carries_phase_diagnostics`); kvm symlink set covers `test_node.py` so the guard runs on CI too.**

## Workflow follow-up

- Archive this change only after 4.2 (two consecutive Travis kvm greens) — `openspec archive fix-kvm-join-cascade-ci`.
- If §1 evidence changes the plan's Phase 1/2 assumptions (e.g. root cause is the kubeadm-config drift of Phase 2, not the join pipeline), update `docs/ca-powered-kubernetes-plan.md` sequencing before starting the next phase's change.

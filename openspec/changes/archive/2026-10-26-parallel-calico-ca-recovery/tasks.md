## 1. Parallel recovery behavior

- [x] 1.1 Define `calico_recovery_max_unavailable: "100%"` in
  `defaults/main.yml` and patch it with the CA-fingerprint annotation in the
  same `kubernetes.core.k8s` task.
- [x] 1.2 Document the parallel rationale, measured handoff, and accepted
  data-plane interruption in the recovery task header.

## 2. Self-diagnosing timeout rescue

- [x] 2.1 Collect Calico pods, cluster nodes, the DaemonSet generation state
  (`status.observedGeneration`, desired/updated/ready counts), and a single
  namespace-wide Event list in the rescue block.
- [x] 2.2 Build a failure message that names nodes without a Ready Calico pod
  and emits safe, per-non-Ready-pod evidence from the in-memory Event filter.
  Default every optional Kubernetes object path to a visible placeholder.
- [x] 2.3 Add a focused runtime regression guard with fixture data for the
  rescue expressions: Ready-condition filtering, event ordering and fallback,
  generation-state extraction, native list/integer handling, cluster-order
  node reporting, and the all-Ready fallback. A syntax check alone does not
  evaluate Jinja task arguments. Implemented as
  `tests/test_calico_recovery_rescue.py` (runs the extracted rescue block
  against fixture facts with the role's venv `ansible-playbook`; covers the
  Ready-condition filter, event ordering/fallback, generation extraction,
  native list/integer handling, cluster-order node reporting, the all-Ready
  fallback, and the fail-message contract).

## 3. Two-profile verification

- [x] 3.1 Create `molecule/parallels-sequential/` from the `parallels`
  topology, setting only `calico_recovery_max_unavailable: "1"`; share
  identical preparation and test assets without duplicating their content.
- [x] 3.2 Confirm Molecule discovers the scenario and syntax-check both
  parallel and serial converge playbooks.
- [x] 3.3 Verify the rescue queries against a live cluster and confirm the
  DaemonSet status fields and Event ordering shape match the failure report.
  (Verified on the live parallels cluster, K8s v1.36.5: DS fields
  generation/observedGeneration/desired/updated/ready all present and
  numeric; events carry lastTimestamp/reason/message/involvedObject despite
  deprecation; pod Ready condition is a string "True"/"False" with message;
  restartedAt annotation confirmed set to the current CA fingerprint.)

## 4. End-to-end validation

- [ ] 4.1 Run the parallel `parallels` destroy, converge, verify, and
  idempotence cycle; verify a CA-triggered rollout completes within the
  timeout and re-converge does not churn Calico pods.
- [ ] 4.2 Run the serial `parallels-sequential` destroy, converge, and
  idempotence cycle; verify it completes within the timeout and the
  re-converge remains unchanged.
- [x] 4.3 Run `openspec validate --all` from the role root.
  Passed: 17/17 items, 0 failed (warnings on pre-existing long requirement
  texts only).
- [x] 4.4 (recorded) The idempotency re-converge failed in
  `ipa-kube-admin-credential`: the keytab export (`ipa-getkeytab` in
  `ipa-cert-renewal.yml`) rotates the principal key as a documented side
  effect, so the managed password is dead by design from the first converge
  onward — yet the probe only tried the password (on the master, not idm),
  so every idempotency run re-asserted the key via `kadmin.local cpw` and
  hit the KDC min-password-age "Too soon" window (silent rc=0 false
  success). Pre-existing design bug, unrelated to the calico change; fixed
  in `tasks/ipa-kube-admin-credential.yml` (probe + verify delegated to idm,
  keytab-first with password fallback for the fresh-install path,
  `failed_when` on "Too soon") and `tasks/ipa-cert-renewal.yml` (keytab
  gate on usability, not file presence, so a stale keytab self-heals);
  `openspec/specs/ipa-kube-admin-credential/spec.md` updated to match.

## 5. KVM cross-host gate (cluster-wide calico wait times out on CI)

- [x] 5.1 Confirm the root cause from the CI rescue `fail` line:
  `ContainerCreating` / slow CNI init → the cross-host gap in 5.2 (or a KVM
  timeout calibration); `CrashLoopBackOff` / x509 / CNI error → a genuine CNI
  fix instead.
  Confirmed from build #95 (job 641223251, the only build that reached the
  calico gate): the DS fatal snapshot at the 300s budget shows
  `observedGeneration=2, updated=1/2, ready=1/2` with both nodes Ready
  pre-patch (`kubectl get nodes` at 08:54:16) — the slow-CNI-init branch
  (CrashLoop/x509 on the new template would count as `updated=2`, and node1's
  kubelet already ran the post-swap CA). The `fail` line itself was never
  emitted (`travis_wait 70` killed the job mid-evidence-collection), so the
  pod-level phase confirmation lands on the next CI failure via the improved
  rescue (2.1/2.2). Response taken: the 5.2 cross-host gate + the KVM timeout
  calibration (rollout 600s, gate 60×10s).
- [x] 5.2 Add an all-nodes Ready gate (cluster-wide `Node` `k8s_info`, not
  master-only) before the cluster-wide `calico-ca-recovery` patch, so the
  post-patch wait is bounded to CNI init on the KVM single order-tolerant play
  (master + single worker converge concurrently). Keep the KVM
  `calico_recovery_max_unavailable: "100%"` parallel full-reset; `parallels`
  (sequential plays) is unaffected. See design.md D4.
  Implemented in `tasks/calico-ca-recovery.yml` (cluster-wide `Node`
  `k8s_info`, all-Ready `until`, `calico_recovery_phase` fact set once the
  gate passes); default budget 30×10s; KVM overrides the gate to 60×10s
  (600s) to match the committed `kubernetes_rollout_wait_timeout: 600`
  override; rescue names the gate phase and the not-Ready nodes.

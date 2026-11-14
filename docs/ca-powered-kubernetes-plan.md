# CA-Powered Kubernetes — Plan to a Definitive, Best-in-Class Result

Status: **thinking artifact** (explore mode). Not a spec; each phase is intended to become
its own OpenSpec change. Grounded in the role as of HEAD `c5694a6`
(Nov 2026, kvm/Travis CI join failure under investigation).

## Definition of Done

What "definitive" means, as a scoreboard every phase maps onto:

| # | Property | Proof mechanism |
|---|----------|-----------------|
| D1 | Full molecule cycle green on **all** scenarios (parallels, parallels-sequential, kvm) + reconverge idempotent | molecule / CI |
| D2 | **FreeIPA is the single signer.** Every byte of trust material in the cluster traces to CA #1 (`kubernetes-ca`) / CA #2 (`kubeclusteradm`); the kubeadm self-signed CA is dead on all hosts and **no path resurrects it** | tests + Phase 2 drift gate |
| D3 | Unattended cert lifecycle: renewals happen, are observable, and survive a forced full-cluster renewal drill | verify suite |
| D4 | **Workload-level proof**, not just component liveness | smoke tests (Phase 4) |
| D5 | Any failure produces a **named diagnosis + captured artifacts**, never a generic message; node failures never cascade from a master failure | structured gates (Phase 1) |
| D6 | Operator runbooks exist and were exercised (CA rotation, cert-expiry emergency, node rejoin, etcd restore) | docs + CI drills (Phase 5) |

## Trust model recap (current design, for orientation)

- CA #1 `kubernetes-ca` — signs the API server **serving** cert (trust anchor for kubeconfigs).
- CA #2 `kubeclusteradm` — signs **all client** certs: front-proxy,
  apiserver-kubelet-client, controller-manager, scheduler, cluster-admin,
  per-node kubelet clients (`kubernetesNodes` profile adds `system:node:` prefix).
- `ca-bundle.crt` (CA #2 + CA #1) — `--client-ca-file`, `--root-ca-file`,
  kubelet `clientCAFile`.
- KCM CSR signers disabled (`--cluster-signing-*-file=` emptied); kubelet
  bootstrap/rotation removed (drop-in `20-orchestration.conf`,
  `rotateCertificates: false`). FreeIPA is the only signer by design.
- Kubeadm self-signed CA retired post-swap (`ca.crt.kubeadm`, `ca.key`,
  gate anchor deleted).
- Renewal: systemd timer `kube-cert-renew.timer`, keytab-first
  (`/etc/krb5.keytab` host principals; `kubeclusteradm` keytab for admin),
  eligibility-gated (`RENEW_THRESHOLD_DAYS`, default 30), private keys reused,
  subjects rewritten by IPA profiles.

## Phase 0 — Green the current CI (prerequisite)

The kvm/Travis failure is a **cascade**: a master-side hard failure inside
`tasks/certs/ipa-certs.yml` (exact task unknown — needs the **first `fatal:`**
from the full log) drops the master from the single play; node1 then times out
its join gates and dies at `tasks/kube-install-join-node.yml` rescue with the
generic "kubelet not active" message.

1. Extract the first `fatal:` from the Travis log → discriminates the
   candidate root causes (master cert chain vs. new CA #2 fetch race vs.
   120s gate starvation on the constrained runner).
2. Re-run the same commit → flake vs. deterministic.
3. Add **failure artifact capture** (Travis `after_failure` or molecule
   side-effect): `journalctl -u kubelet` **since block start** (the current
   rescue `journalctl -n 2000` tail already misled this investigation),
   `crictl pods`/`ps`, gate probe outputs, `ipa-getcert`/keytab state.

**Exit:** two consecutive Travis greens on the commit.
**OpenSpec change:** `fix-kvm-join-cascade-ci`.

## Phase 1 — Failure isolation + diagnosability in the join pipeline

Today: one play over `kube_master,kube_node` with `when:` group gating. Serial
order is correct, but **failure attribution is broken** (this CI incident: a
master death surfaces minutes later as a node timeout).

- Split into ordered plays: `master-core` → `master-certs` → `nodes-join` →
  `master-finalize`, with `any_errors_fatal` per play. Keeps the ordering
  contract, kills the cascade.
- **Per-gate budgets from measurements**, not one global
  `kubernetes_api_ready_retries: 12` (today the same knob governs the master
  API gate — 120s, tight on a shared runner — and the post-swap gates).
  Exponential backoff; every timeout message names *what it waits for and who
  provides it*.
- Make the node's **CA #2 fetch resilient** — it is a hard fatal with no
  retry (`ipa ca-show kubeclusteradm`, added by `c5694a6`); the old
  single-CA profile gate never covered CA #2's existence, so a new race was
  introduced alongside the CA #2 node dependencies.
- Rescue path emits a structured diagnostic bundle per host instead of a
  journal tail.

**Exit:** deliberately break one master task upstream of a node gate → the node
play fails *immediately* with a message naming the upstream gate; artifacts in
the CI log.
**OpenSpec change:** `join-pipeline-failure-isolation`.

## Phase 2 — Trust-plane integrity: kill the kubeadm-upgrade landmine

**The hidden defect.** The CA swap patches the **static-pod manifests only**
(`tasks/certs/ipa-certs.yml` rewrites `--client-ca-file`, `--root-ca-file`, and
empties `--cluster-signing-*-file=`). The `kubeadm-config` ConfigMap's
`ClusterConfiguration` is never touched (zero hits for `kubeadm-config` in
`tasks/`). Consequences:

- The next `kubeadm upgrade apply` **regenerates the control-plane manifests
  from the etcd-stored config and resurrects every kubeadm-CA reference**: KCM
  points back at the deleted `ca.key` and dies; the API server's client CA
  reverts to CA #1 only and starts rejecting every CA #2 client (all kubelets,
  admin) — a self-inflicted outage from a routine minor upgrade.
- `kubeadm certs check-expiration` / `kubeadm certs renew` are broken or
  misleading (they expect the kubeadm CA + key in `/etc/kubernetes/pki`).

Work items:

- Reconcile `kubeadm-config` `extraArgs` via the API (`kubernetes.core.k8s`):
  apiServer `client-ca-file`/`root-ca-file` → `ca-bundle.crt`; controllerManager
  cluster-signing → empty. Regeneration becomes safe by design.
- Add a **drift fitness test**: ConfigMap `extraArgs` == on-disk manifest flags.
- Document the signer policy explicitly: FreeIPA is the sole signer; KCM CSR
  signers stay disabled (this is why `rotateCertificates: false` and the
  kubeadm drop-in removal exist); give add-ons (metrics-server, cert-manager)
  the pattern of getting certs from FreeIPA profiles instead of the KCM signer.

**Exit:** rendering the control-plane manifests from the patched ConfigMap
reproduces the patched flags; the drift test is in the verify suite.
**OpenSpec change:** `kubeadm-config-trust-drift`.

## Phase 3 — Certificate lifecycle (still working in year 2)

The timer + keytab-first + eligibility gating is solid; the gaps are around it:

- **Renewal liveness telemetry.** The silent failure mode: broken keytab or
  down IPA → timer no-ops → certs die in ~1 year. Add (a) verify-time
  assertion that the timer's last tick succeeded and the last log line is
  fresh, (b) node_exporter textfile-collector metric per cert `notAfter` with
  alert thresholds (45/30/14 days).
- **Full-cluster renewal drill in verify.** Today only node-client forced
  renewal (`test_cert_renewal_forced_eligibility_extends_node_client`) and the
  noop ticks are covered. Extend: force-eligible renewal of *every* cert
  (apiserver, front-proxy, KCM/scheduler, admin, node clients) → assert static
  pods restarted, KCM lease fresh, all nodes Ready, bundle still validates.
  Highest-value single test for a CA-powered system.
- **CA rotation readiness.** Script the bundle rebuild (fetch both CA certs
  from IPA, diff against `ca-bundle.crt`, redistribute atomically, restart
  dependents) + runbook. dogtag CA renewal is IPA's job; cluster-side trust
  propagation is this role's.
- `logrotate` for `/var/log/kube-cert-renew.log` (currently unbounded).

**Exit:** renewal drill green in CI; expiry floor asserted (all certs ≥ N days
after converge).
**OpenSpec change:** `cert-lifecycle-observability-drill`.

## Phase 4 — Workload-level verification (D4)

The 60-test suite proves components and cert identities; it does not prove the
**cluster works as a cluster**:

- `kubectl exec` + `kubectl logs` against pods on **both** master and worker —
  end-to-end proof of the exact path the bundle exists for (API server's
  CA #2-issued `apiserver-kubelet-client` cert ↔ kubelet
  `clientCAFile: ca-bundle.crt`). Today only the master side is patched/gated.
- Deployment spanning both nodes → ClusterIP service → DNS (exists) →
  NodePort; NetworkPolicy deny/allow; hostNetwork pod.
- Keep the NFS PV tests; add a pod-reschedule-after-restart persistence check.
- Post-reboot resilience: reboot all VMs once in the verify phase, re-run the
  smoke suite (proves the swapped trust plane survives cold start).

**Exit:** any trust-plane regression fails at least one workload test, not
just an identity grep.
**OpenSpec change:** `workload-smoke-verification`.

## Phase 5 — CI maturity + operations (D6)

- Nightly full matrix (parallels + parallels-sequential + kvm); PRs run kvm
  only. Flake ledger with per-gate p95 tracking so budgets come from
  measurements, never "raise the timeout until Travis passes".
- **etcd backup automation**: daily snapshot to NFS + retention + a tested
  restore drill job. Not definitive without it.
- Runbooks under `src/site/asciidoc/admin/` (via `/update-platform-docs`):
  the CA state machine (kubeadm-CA → dual-trust → IPA-only), cert-expiry
  emergency, node rejoin (`reset_kube` path), CA compromise/revocation —
  Kubernetes has no CRL checking, so the revocation model is "renew with a new
  key + block re-enrollment via CA ACL/profile" — disaster recovery.
- Pin ansible-core/python in CI; make `tox -e idempotence-monorepo` a hard
  gate.

**OpenSpec change:** `ci-artifacts-backup-runbooks`.

## Sequencing & governance

| Order | Phase | OpenSpec change | Depends on |
|-------|-------|-----------------|------------|
| 1 | 0 | `fix-kvm-join-cascade-ci` | — |
| 2 | 1 | `join-pipeline-failure-isolation` | 0 |
| 3 | 2 | `kubeadm-config-trust-drift` | — (parallel with 1) |
| 4 | 3 | `cert-lifecycle-observability-drill` | 2 |
| 5 | 4 | `workload-smoke-verification` | 1 |
| 6 | 5 | `ci-artifacts-backup-runbooks` | 1–4 |

All changes live in this role's `openspec/`, except items that belong to
`tcharl.freeipa_server` / `tcharl.kubernetes` (monorepo rule 4: the proposal
goes on the target role).

## Explicit non-goals (choices, not omissions)

- **Single control plane.** HA stacked-etcd + VIP/LB is a separate initiative.
- **Kubelet *serving* cert via FreeIPA** (`kubeletServing` profile +
  `--kubelet-certificate-authority`): natural follow-up to Phase 2, deferred;
  today the API server does not verify kubelet serving certs.
- **etcd cert migration.** The kubeadm etcd CA stays — an isolated plane;
  migrating it to FreeIPA is not required by the single-signer goal (etcd
  trusts nothing outside its own CA).

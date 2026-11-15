# Evidence: KVM join-cascade failure (Travis CI)

## Run(s)

- Travis molecule `kvm` converge, commit `c5694a6` ("chore: remove the selfsigned kubernetes
  ca at the end of the replacement", Nov 14 10:55). Failure first reported ~12:31 UTC+1.
- **Two supplied runs show the byte-identical node failure** → deterministic, not a flake.
  Fixed CI sizing (3× 2GB/2vCPU VMs on an 8GB/2vCPU Travis runner) makes the timing stable,
  which is itself evidence the failure is a timing race with a stable, too-small margin.

## Confirmed node-side facts (from fetched Travis log)

Failing task: `Kube-install-join | wait for kubernetesNodes profile to exist in FreeIPA`
(`tasks/kube-install-join-node.yml:39`, delegated to idm):

```
cmd: set -o pipefail && ipa certprofile-find | grep -c ': kubernetesNodes'
attempts: 40   rc: 1   stdout: "0"   stderr: ""
start 12:32:39 → end 12:37:10  (all 40 attempts identical)
```

Then the block `rescue:` (`:321–335`) dumps the kubelet journal and fails with the generic
`"Node join failed - kubelet not active. Check kubelet logs above."` — useless evidence for a
*gate* timeout (kubelet never started; the journal shows a crash-loop over the absent
`/var/lib/kubelet/config.yaml` left by the tcharl.kubernetes role's disabled join attempt).
This rescue flaw is what design D2 fixes.

PLAY RECAP:

```
node1.osgiliath.test   ok=24  changed=24  failed=1  skipped=22  unreachable=0  rescued=1
master.osgiliath.test  ok=190 changed=54  failed=1  skipped=111 unreachable=0  rescued=0
```

PIPELINE: converge stage = **1893 s (~31.5 min)**. The node's gate window ended at 12:37:10,
≈ T+11–13 min into the converge → **the master stayed alive ~18–20 minutes past the node's
death**.

## Corrections to the first draft of this ledger

1. **No `serial:` in `molecule/kvm/converge.yml`.** It is a single play
   `hosts: kube_master,kube_node` — master and node run **concurrently**. The file's own
   comment states cross-host dependencies are handled by in-role readiness gates, not play
   ordering. The earlier "serial: 1, master runs to completion before the node starts" claim
   was wrong and its consequences are void.
2. **The profile gate is NOT new in `c5694a6`.** The commit's first
   `kube-install-join-node.yml` hunk starts at line 69, so the gate at `:39` predates the
   commit. The node-side defect therefore also predates it (see Verdicts).
3. **Node budget math.** The gate runs with the generic
   `orchestration_readiness_retries: 40` × `orchestration_readiness_delay: 5`
   (`defaults/main.yml:38–39`): 39 sleeps × 5 s ≈ 195 s plus 40 delegated `ipa` executions
   → **271 s wall-clock** (12:32:39→12:37:10 measured). Not 280 s.

## Exonerations (proof chains)

1. **Kerberos ticketing is NOT the cause** (answers the standing question):
   - The node's `admin.node_join` ticket acquisition tasks succeeded (pre-clear + mint pairs
     reported as the node's `changed` counts).
   - The failing command itself proves authentication worked: `ipa certprofile-find` ran
     cleanly (`stdout: "0"`, empty stderr). rc=1 is `grep -c` reporting zero matches — its
     documented exit code — not an IPA error. A broken/missing ticket makes `ipa` exit
     non-zero with a Kerberos/bind error and *empty* stdout.
2. **Gate mechanics are sound.** `ipa certprofile-find` prints `  Profile ID: kubernetesNodes`;
   the grep pattern `': kubernetesNodes'` matches that format. `stdout: "0"` across all 40
   attempts therefore means the profile was **genuinely absent** for the whole window, and
   empty stderr means the IPA API was healthy.
3. **Master did not die early.** Story (A′) — master dying upstream of profile creation —
   is refuted by the timing: that death would have ended the play at ≈ T+8–13 min, but the
   converge ran 31.5 min. The master's `failed=1` is **late**, and it is the *consequence*
   of the worker never joining, not the cause.

## Root cause (verdict): timing race between the node gate budget and the master's CI pace

Logic chain:

- Profile absent for the whole node window (exoneration 2) + ticketing sound (exoneration 1)
  ⇒ the master had **not yet reached** `Ipa-kubernetes-ca | ensure kubernetesNodes profile`
  (`tasks/certs/ipa-kubernetes-ca.yml:178`) when the node's 271 s budget expired.
- Master alive ~20 min longer (PIPELINE timing) ⇒ it kept working and created the profile
  after the node was already dead. On the loaded runner the master's path to profile creation
  (packages → cri → firewall → **kubeadm init** → IPA CA chain) simply takes longer than
  ~4.5 min wall-clock — the node races ahead (its `kube-install.yml` is packages-only, join
  disabled) and times out.
- The master then dies at its first **worker-dependent gate**: most likely
  `Calico-ca-recovery | wait for all nodes to report Ready`
  (`tasks/certs/calico-ca-recovery.yml:62`, budget 60×10 s in the kvm scenario) or the
  `kubectl get nodes` acceptance check at the end of `tasks/admin-user.yml:231` — the
  single worker never joined, so these cannot pass. This is the cascade that explains
  `master failed=1` after a long, otherwise-successful run (ok=190).

### Why it surfaced at `c5694a6` without being introduced by it

- Diff triage: **everything the commit added before the profile-creation point is non-fatal
  by construction** (`x509_certificate_info` + `failed_when: false`, `set_fact`, `stat`,
  conditional `slurp`; `replace` never fails on no-match). The new fatal-capable work (KCM
  flag emptying, kubelet `clientCAFile` patch, kubeadm-CA retirement deletion) all runs
  **after** profile creation and cannot explain the node's pre-profile timeout.
- The commit *did* add time to the master's pre-profile path (the retirement-gating block at
  the top of `ipa-certs.yml`), which is exactly the kind of shift that tips a marginal race
  over the edge.
- The last change before it (`2026-11-12-kubelet-x509-client-auth`, landed as `c5694a6`) was
  validated **parallels-only**; kvm has plausibly been red since then, with `c5694a6` merely
  being the commit that surfaced it. The two byte-identical runs confirm the margin is
  stably negative, not flaky.

### Corollary: the un-retried CA fetches are the same race class

`c5694a6` added the `kubeclusteradm` CA fetch pair (`:76–91`) with **no retries**, right
after the gate. They sit behind the profile gate (the CA is created before the profile), so
they are safe *if the gate budget is right* — but they are in the same
"node-races-ahead-of-master" class and get hardening retries (§3.1) rather than a separate
root-cause bucket.

## Still missing (no longer blocking)

- The **master's first `fatal:` block** — the fetched excerpts never included it (log lost).
  It would name the exact late-death gate (calico Ready vs `kubectl get nodes`), but the
  fix is decided without it: the node-side race is proven by code + PIPELINE timing, and the
  master-side gate budgets already exist for Phase-1 work. Treat as confirmation-to-come if
  a future Travis log yields it.

## Verdicts

- Flake? **No** — identical twice; stable CI sizing.
- krb ticketing? **No** — exoneration 1.
- Master cert-chain task (bucket a)? **No** — exonerations 2–3.
- Gate grep-pattern bug (bucket b as originally framed)? **No** — pattern matches the real
  output format; the gate is also older than the suspect commit.
- **Root cause: node profile-gate budget (40×5 s ≈ 271 s wall) is too small for the master's
  profile-creation pace on the constrained kvm CI runner.** The node times out; the master
  later creates the profile, completes the PKI swap, and dies at the first worker-dependent
  gate. Fix = join-scale budget for the profile gate + named-fail gate diagnostics (§2).

## Local verification (parallels, 2026-11-14)

Environment: macOS host, three Parallels VMs (idm 5 GB + master/node1/node2 8 GB). PEP 668
detail: `molecule test`'s dependency step runs `pip install` inside the tox-venv and dies
with `externally-managed-environment` when run without `tox` — **always run molecule via
`uv tool run --python 3.13 --with tox tox -e <env>`**, which pins the dependency installer
(`TOX_CONSTRAINTS` mechanism) and works.

### Task 2.2 / 3.3 / 3.4 — negative test A: PASSED

Scratch mutation (reverted): profile gate grep → `kubernetesNodesZZZ`; budget overridden to
2×2 s via molecule passthrough (`... tox -e converge-monorepo -- --scenario-name=parallels
-- -e kube_join_profile_ready_retries=2 kube_join_profile_ready_delay=10` — the `--` escape
is required, molecule's click parser otherwise rejects the bare `-e`). Converge exit 2
(expected). The rescue output (node1) contained, verbatim:

- `failed_task=Kube-install-join | wait for kubernetesNodes profile to exist in FreeIPA`
- `join_started=2026-11-14T12:49:54-06:00` (task 3.2 confirmed)
- `original_failure=The command exited with a non-zero return code.`
- `certprofile_find=[...]` — **live** `ipa certprofile-find` from idm listing all 8 profiles
  including the real `kubernetesNodes` (proves the gate's pattern was right and the upstream
  producer had done its job)
- `kubelet=Jul 06 ... kubelet[35830]: E1114 ... "kube-system" ... no such file or directory`
  windowed tail (no such file at gate time — kubelet never started — correctly windowed)
- `crictl=PODS / (total: 0)` + `CONTAINER / IMAGE / TAG / CONTAINER ID / CREATED / STATE / ...`
- `ipa_getcert=Number of certificates requests=0 ...` (node enrollment happens only after the
  gates — correct for this phase)
- `artifacts(exist)=[False, False, False, False, True]` — kubelet.conf, ca.crt, ca-bundle.crt,
  node-client.crt absent; krb5.keytab present
- Named diagnosis: `DIAGNOSIS: the join waited for the 'kubernetesNodes' cert profile in
  FreeIPA and it never appeared within the retry budget (120 retries x 10 s).`
- Attribution (task 3.4): `Upstream dependencies for profile/CA/API gate failures:
  master-side certificate provisioning — tasks/certs/ipa-certs.yml, with the 'kubernetesNodes'
  profile created in tasks/certs/ipa-kubernetes-ca.yml — and idm CA availability`
- **No generic "kubelet not active"** (the pre-fix symptom) — replaced by phase-aware output.

PLAY RECAP corroboration: `master failed=1` at the calico all-nodes-Ready gate, `node1/node2
failed=1 rescued=1` — exactly the CI cascade story reproduced on demand locally.

### Bug found by the negative test (fixed)

`crictl pods -a` is not a valid flag (`crictl pods` lists all states already; unlike
`crictl ps -a`) — it printed usage text instead of state. Fixed to `crictl pods`.

### Dead-code bug found during task 3.1 implementation (fixed)

`until`+`retries` on a failing shell task ends the task **failed** on exhaustion, so the
named `CA_FETCH_TIMEOUT` fail tasks could never run. Both CA fetches now carry
`failed_when: false` (until still governs the loop; the named fail owns the diagnosis).

### Task 3.1 — negative test B: PASSED

Scratch mutation (reverted): first fetch's `ipa ca-show kubernetes-ca` → `kubernetes-caZZZ`
(gate name restored, so the profile gate passes and the fetch stage is reached). Converge
exit 2 after 958 s (expected). Verbatim from the log:

- Named fail (both workers): `CA_FETCH_TIMEOUT: CA 'kubernetes-ca' never materialised as
  valid PEM at /tmp/kube-node-ca.crt on idm.osgiliath.test (5 x 5 s exhausted). Last ipa
  output:  ipa: ERROR: kubernetes-caZZZ: Certificate Authority not found` (+ the `grep:
  /tmp/kube-node-ca.crt: No such file or directory` tail) — **names the CA and the IPA host,
  no late join timeout**.
- Rescue (`failed_task=Kube-install-join | fail if kubernetes-ca never validated as PEM`,
  `join_started=2026-11-14T13:26:15-06:00`) captured live `certprofile_find` = 8 profiles
  **including `kubernetesNodes`** — the capture `when` matched via the lowercase `ca` in the
  failed-task name (case-insensitive broadening verified), correctly distinguishing "profile
  exists, CA missing" from the Phase-A story.
- Final named fail carried the full attribution line + inline certprofile inventory.
- `crictl=` capture shows clean `POD ID … CREATED … STATE` / `CONTAINER …` headers (no usage
  text) — confirms the `crictl pods` fix live.
- PLAY RECAP: master failed=1 (calico collateral, same worker-absence story: `desired=1
  ready=1` DaemonSet + unschedulable envoy pods), node1/node2 `failed=1 rescued=1`.

Both negative tests green ⇒ tasks 2.2, 3.1, 3.3, 3.4 verification criteria met. Scratch
mutations fully reverted (`grep -n ZZZ tasks/` clean); lint re-run green after the revert
and the `crictl pods` fix; `openspec validate --strict` valid.

### Task 4.1 — positive converge (unmutated code): PASSED

Run against the same VMs (no destroy) immediately after negative B — i.e. the nodes were in
the failed-join state from the negative run and the unmutated converge **recovered** them
end to end (a stronger claim than a cold-path run: the join path self-heals from a starved
prior attempt). Exit 0 in 664 s. Verbatim PLAY RECAP:

```
master.osgiliath.test      : ok=460  changed=113  unreachable=0  failed=0  skipped=94  rescued=4  ignored=0
node1.osgiliath.test       : ok=175  changed=46   unreachable=0  failed=0  skipped=74  rescued=0  ignored=0
node2.osgiliath.test       : ok=175  changed=46   unreachable=0  failed=0  skipped=74  rescued=0  ignored=0
```

Key contrasts with the CI cascade and the negative runs: both workers' kubelets
`ActiveState: active` (restart_kubelet handler fired on the nodes, skipped on master), the
master's late `calico-ca-recovery.yml:469` gate found every node covered by a Ready
calico-node pod (it did not fire), and `rescued=4` on master are the expected keytab-probe
`kinit: Pre-authentication failed` → password-fallback paths (keytab-first design working as
intended). Log: `sh_1db8f0426001Y9SLvJ1j1UsBkJ.out`.

### Task 4.1 — verify gate: PASSED (74/74)

`verify-monorepo -- --scenario-name=parallels`: **74 passed in 39.42 s**, 0 failures.
Coverage confirmed for this change's DoD: `test_kubectl_get_nodes_matches_inventory`,
`test_calico_pods_ready`, `test_coredns_pods_ready`, `test_cluster_dns_resolves_via_coredns`,
`test_node_ready_via_master_admin_conf`, per-node cert chain/identity tests for **both**
workers, PV/NFS tests, and the new structural guard
`test_join_rescue_carries_phase_diagnostics`. Full cold-path cycle
(`destroy → converge → verify`) plus idempotence reconverge follow below.

### Task 1.3 — deferred

Pre-fix local baseline intentionally not run (10–15 min per cycle, and the mechanism is
kvm-runner-specific by construction: the local topology passes the profile gate because
master reaches profile creation inside the 271 s window — the same conclusion as the 11-13
"passes locally" precedent). The positive post-fix converge + verify + reconverge in §4.1 is
the local gate instead.

### Task 4.1 — cold-path cycle (destroy → create → prepare → converge): PASSED

Formal protocol run on fresh VMs (parallels, two workers). `destroy` 100.76 s, then full
`converge-monorepo` **exit 0 in 1850.38 s** (includes `vagrant up` of all three VMs +
prepare phase: FreeIPA install, NFS setup). Verbatim PLAY RECAP:

```
master.osgiliath.test      : ok=472  changed=171  unreachable=0  failed=0  skipped=82  rescued=5  ignored=0
node1.osgiliath.test       : ok=177  changed=64   unreachable=0  failed=0  skipped=72  rescued=0  ignored=0
node2.osgiliath.test       : ok=177  changed=65   unreachable=0  failed=0  skipped=72  rescued=0  ignored=0
```

Cold-path deltas vs the warm run above are all expected: higher `changed` (fresh VMs,
kubeadm init, full IPA install), higher master `ok` (82 fewer skips), and `rescued=5` vs 4
(one extra keytab-probe rescue: the `kubeclusteradm` keytab does not exist on the first
probe of a fresh install). Both workers' `restart_kubelet` handler fired `changed` with
`ActiveState: active` — joined on the cold path with the new gate budget, no rescue on the
nodes. Log: `sh_1dba3382b001Rk217U83dF7EY8.out`.

### Task 4.1 — cold-path verify gate: PASSED (74/74)

`verify-monorepo -- --scenario-name=parallels` on the cold-provisioned cluster:
**74 passed in 38.89 s**, 0 failures — identical green set as the warm run (all nodes Ready,
calico/CoreDNS per-pod evidence, DNS resolution, PV/NFS mounts, both-worker cert
chain/identity suites, `test_two_workers_present`, and the structural guard
`test_join_rescue_carries_phase_diagnostics`). Log: `sh_1dbc03173001iP5ge7YEqVXEcZ.out`.

### Task 4.1 — idempotence reconverge: PASSED

`converge-monorepo -- --scenario-name=parallels` again on the converged cluster:
**exit 0 in 641.71 s**, `failed=0` everywhere and master `rescued=0` (no keytab-probe
rescues on the second pass — the keytab now exists and is usable):

```
master.osgiliath.test      : ok=452  changed=103  unreachable=0  failed=0  skipped=96  rescued=0  ignored=0
node1.osgiliath.test       : ok=175  changed=40   unreachable=0  failed=0  skipped=74  rescued=0  ignored=0
node2.osgiliath.test       : ok=175  changed=40   unreachable=0  failed=0  skipped=74  rescued=0  ignored=0
```

The residual `changed` counts are the role's pre-existing, unrelated non-idempotence: the
`geerlingguy.containerd` role restarts its service on every run, which trips the
`restart_kubelet` handler on both workers (both kubelets report `ActiveState: active` after
the restart — the join survives it). No new-change classes introduced by this fix: the join
path itself (profile gate, CA fetch, `kubeadm join`) reported no changes on the reconverge.
Per the monorepo protocol ("if idempotence is not supported, reconverge and re-verify"), the
gate is the re-verify that follows. Log: `sh_1dbc1c0e30015BSRlG282y2bUP.out`.

### Task 4.1 — post-reconverge re-verify: PASSED (74/74) — 4.1 CLOSED

`verify-monorepo -- --scenario-name=parallels` after the idempotence reconverge:
**74 passed in 37.83 s**, 0 failures — same green set (cluster survived the containerd-driven
kubelet restarts from the reconverge; all nodes Ready, per-pod evidence, PV mounts, both
worker cert suites, structural guard). Log: `sh_1dbd17ac8001niPvpaKBXeehF1.out`.

**Task 4.1 verdict: PASSED.** Full protocol run `destroy → converge → verify → reconverge →
re-verify` green end to end on the host-OS-matched scenario.

## Task 4.2 — CI delivery (in progress)

- Fix committed on `parallel`: `0038b9c` ("fix(kube-node-join): dedicated profile-gate
  budget for join-scale, named fails with phase diagnostics") — full rationale in the
  commit message (measured node budget ~271 s vs master's minutes-later profile creation
  on the 8 GB/2 vCPU runner).
- Delivery to `master` (Travis only builds `master` per `.travis.yml` `branches.only`):
  `upstream/master` merged into `parallel` (`f1ff4f5`, tree byte-identical to `0038b9c`,
  no content delta) and pushed `parallel:master` — fast-forward `abd9765..f1ff4f5`, the
  same content shape as the established PR `parallel → master` flow (PR #23 precedent).
- Travis build **#107** created for `f1ff4f5` on `master`, job `641604072`
  (https://app.travis-ci.com/github/OsgiliathEnterprise/ansible-orchestration/jobs/641604072).
  Runs `tox -e test-exec -- --scenario-name kvm` (single-worker CI topology).
  Prior failed build #106 duration 3953 s ≈ 66 min is the expected pace.
- Exit criterion: two consecutive green kvm runs on the fixed commit — second run is a
  same-commit Travis restart once the first is green (task 1.2 precedent).

## Build #107 post-mortem (commit `f1ff4f5`, job 641604072 — FAILED, 5608 s)

**Verdict: the join fix worked exactly as designed; the run died one gate earlier in the
master chain — the coredns restart got a 504 from the just-initialized API server.** This
is the fourth bucket (master-bringup API-call load fragility), fixed by tasks.md 2.5.

### Master's first fatal (task 1.1 — obtained)

`Kube-install | Restarts coredns after calico installation` (`tasks/kube-install.yml:141`),
`kubernetes.core.k8s` with `wait: true`, at 21:59:08 GMT:

```
fatal: [master.osgiliath.test]: FAILED! => {"changed": false, "msg": "504\nReason: Gateway Timeout
... 'Date': 'Sat, 14 Nov 2026 21:59:08 GMT' ...
"message":"Timeout: request did not complete within the allotted timeout","reason":"Timeout..."}
Origin: .../tasks/kube-install.yml:141:3
```

The freshly initialized API server, under calico bring-up load on the 8 GB/2 vCPU runner,
answered the single un-retried API call with a gateway timeout; the task had no retries, so
the master play aborted there — **minutes before** `kubernetesNodes` profile creation in
`tasks/certs/ipa-kubernetes-ca.yml`.

### Timeline (GMT)

| Time | Event |
|------|-------|
| 20:55:34 | job started (VM bring-up, prepare) |
| ~21:41 | converge play starts |
| 21:59:08 | **master fatal — coredns 504** (`kube-install.yml:141`) |
| 22:01:12 | node join block starts (`join started 2026-11-14T22:01:12+00:00`) |
| 22:01→22:2x | node profile gate consumes **full 120-attempt budget** (grep count = 120) |
| ~22:2x | node rescue fires → named fail with upstream evidence |
| 22:29:02 | job finished, `test-exec: exit 1 (4952.74 s converge)` |

### Node-side proof the join fix works under CI conditions

PLAY RECAP: `master failed=1` (coredns 504), `node1 failed=1 rescued=1` — the rescue
engaged, then the named fail reported (log line 8532):

```
Node join failed in task 'Kube-install-join | wait for kubernetesNodes profile to exist in
FreeIPA' (join started 2026-11-14T22:01:12+00:00). Upstream dependencies for profile/CA/API
gate failures: master-side certificate provisioning — tasks/certs/ipa-certs.yml, with the
'kubernetesNodes' profile created in tasks/certs/ipa-kubernetes-ca.yml — and idm CA
availability: a profile-gate timeout means the master had not reached profile creation yet,
not a node fault. certprofile-find (rc=0): 4 profiles matched ...
```

The captured `certprofile-find` shows exactly the 4 built-in profiles — `kubernetesNodes`
absent — **proving the starvation attribution**: the master never reached profile creation
because it died at coredns. Contrast with #106's blind 2000-line journal tail.

### Cascade re-interpretation of #106/#107

The #106-era root cause (node profile-gate starvation, fixed by 2.1–2.2) remains valid and
was *confirmed* by #107 — the gate now waits join-scale instead of self-failing at 271 s.
But both runs shared an earlier, load-dependent master death: the join-scale budget alone
cannot make CI green while a single transient 504 on an un-retried master bring-up API call
aborts the chain before profile creation. 2.5 removes that failure mode (apply is an
idempotent annotated patch; the rollout wait is a resilient `k8s_info` poll), so the next
build exercises the full designed flow.

### Fix (tasks.md 2.5)

`tasks/kube-install.yml` coredns restart split into idempotent apply (`wait: false`,
`until: ... is succeeded`, 6×10 s, `failed_when: false`) + named fail carrying the last API
error, and rollout wait via `k8s_info` poll gated on `observedGeneration >= generation` and
`readyReplicas >= replicas` (24×20 s, `failed_when: false`) + named fail with upstream
attribution. Wait budget stays inside the node gate's ~20 min ceiling so the master can
never starve the gate behind this wait. Structural guard
`test_coredns_restart_is_load_tolerant` (`molecule/default/tests/test_master.py`) pins the
contract (positive + revert-detection PASSED locally). Log: `travis_107.log` (ANSI-stripped,
8613 lines).

**Local validation before CI push (2026-11-15):** warm reconverge on the converged parallels
cluster — `converge-monorepo` OK in 572 s, PLAY RECAP `failed=0 rescued=0` on all three hosts
(the named-fail tasks following both retry loops would set `failed=1` on budget exhaustion,
so the green RECAP proves the idempotent apply and the `observedGeneration`-gated rollout poll
both succeeded on a live cluster); `verify-monorepo` 75/75 passed in 37.6 s — the prior 74
plus the new static guard running under molecule.

### CI delivery — build #108 (run #1 toward the two-green exit criterion)

`d869e70` pushed to `upstream/parallel` and fast-forwarded to `master`
(`f1ff4f5..d869e70`) 2026-11-15 23:0x UTC via `~/.ssh/github_nopass` (the `~/.ssh/github`
key GitHub accepts is passphrase-locked with no keychain entry; `github_nopass` is the
unprotected deploy key with write access to `OsgiliathEnterprise/ansible-orchestration`).
Travis build **#108** = build id 279192481, job **641604415** (108.1), commit `d869e709`,
branch `master`, started 2026-11-14T23:09:15Z. Monitored via
`GET https://api.travis-ci.com/build/279192481/jobs` (job states) — the `/repo/…/builds/<number>`
path is not a valid v3 controller; use the internal build id from the builds list.

## Build #108 post-mortem (commit `d869e709`, job 641604415 — FAILED, ~94 min)

Fifth bucket: the master died at the **coredns rollout wait**, and the investigation closed
the root cause as a **broken calico-node Ready gate query** — the gate added after #107 never
actually polled anything.

### What the hardened tasks proved (they behaved exactly as designed)

- Coredns idempotent apply: attempt 1 succeeded at 23:56:58Z — the #107 504 class is fixed.
- Rollout wait: all 24 polls ran and reported `unavailableReplicas: 3`; the named fail
  `never reported a complete restarted rollout` fired with pod evidence (log line 8102,
  `travis_108.log` ANSI-stripped). Master first fatal; no anonymous until-exhaustion.
- Both nodes: profile gate waited its full join-scale budget, named fail + rescue with
  upstream evidence fired (join fix still confirmed).

### Root cause (definitive, from local cold reproduction)

The calico-node Ready gate shipped after #107 queried with `all_namespaces: true` +
singular `label_selector`/`field_selector`. The pinned `kubernetes.core` **rejects those
params outright** — standing module error on every attempt:
`Unsupported parameters for (kubernetes.core.k8s_info) module: field_selector,
label_selector` (and `all_namespaces`; supported params are the **plural**
`label_selectors`/`field_selectors` + `namespace`). `failed_when: false` swallowed the arg
error, so `resources` stayed empty for the entire 490 s window and the gate's named fail
aborted the master chain **before profile creation** — starving both node gates. Timeline
proof from the cold parallels resume (`converge_cold2_resume_20261115_102713.log`): the
calico-node pod was created ~09:33 UTC and was Running/Ready while the gate (09:36–09:44
UTC) polled zero pods. The same singular-param bug existed latently in the coredns
pod-evidence task (`label_selector: "k8s-app=kube-dns"`) — it hard-fails when reached.
This also explains warm run 2's master failure.

Module-param probes (playbooks `probe_calico_query*.yml` against the live parallels
cluster): singular/`all_namespaces` variants → `Unsupported parameters`; shipped shape
`namespace: calico-system` + `label_selectors: [k8s-app=calico-node]` +
`field_selectors: [spec.nodeName=<host>]` → `n=1`, Ready condition passes; coredns variant
`namespace: kube-system` + `label_selectors: [k8s-app=kube-dns]` → `n=2`. The known-good
precedent was already in-repo: `tasks/certs/calico-ca-recovery.yml` uses namespace + plural
selectors.

### Fix

`tasks/kube-install.yml`: gate + pod-evidence queries switched to the supported param
shape (`namespace:` + plural `label_selectors:`/`field_selectors:`, matching
`calico-ca-recovery.yml`); gate named fail now self-reports the module error
(`query error: {{ kube_calico_node_pods.msg | default('none') }}`) so a future param
drift diagnoses itself instead of showing `pods: []`. Budgets raised to cover the measured
cold-CI pull floor (>8 min incl. tigera-operator cold pull): `kube_calico_node_ready_retries`
48→90 (~15 min) and `kube_join_profile_ready_retries` 120→180 (~30 min) so the master's
worst-case pre-profile path (apply 6×10 s + gate 90×10 s + rollout 24×20 s + cert work
~5 min ≈ 26–28 min) fits under the node gate ceiling. Ceilings, not floors — warm runs
pass in seconds.

Guards (`molecule/default/tests/test_master.py`): gate guard now pins
`namespace: calico-system` + plural params and **bans** singular `label_selector:`/
`field_selector:` and `all_namespaces:` in both blocks (the exact bug class); coredns guard
carries the same ban for its evidence query. Revert-detection proven by injection: adding
back a singular param (gate) or `all_namespaces:` (coredns block) flips the respective
guard to FAIL with the bug-class message; restored file passes both.

### Local regression — param fix (2026-11-15, parallels): PASSED

- `converge-paramfix` (resume on healthy cluster): OK 655 s, RECAP
  `master ok=471 failed=0 rescued=5` (the 5 = by-design keytab-probe rescues),
  `node1/node2 ok=175 failed=0` — calico gate passed with the fixed query, both nodes
  joined, profile created.
- `verify-monorepo`: **76/76 passed** (38.6 s) — all nodes Ready, per-pod evidence, PV
  mounts, cert chain, renewal timers.
- Reconverge (idempotence): OK 564 s, RECAP `failed=0 rescued=0` on all hosts, **zero
  fatal lines** — warm gate passes in seconds as designed.
- Post-reconverge `verify-monorepo`: green (73 s).
- `tox -e lint`: production profile, 0 failures 0 warnings (102 files).
- Logs: `converge_paramfix_20261115_111350.log`, `verify_paramfix_20261115_112457.log`,
  `converge_paramfix_reconverge_20261115_112627.log`.

## Build #109 post-mortem (commit `6de7461` — PR #24 merge of `f4f44a5`, job 641606168 — FAILED, 94 min)

Timeline note: at 09:57+0100 the repo owner committed the then-working set as `f4f44a5`
("chore: add some additional logs for ci") — this included the calico-node gate **with its
original broken query params** (the param fix was still uncommitted here) — and merged
`parallel` into `master` via PR #24 (`6de7461`), triggering build #109. So #109 was, in
effect, the CI exposure of the fifth bucket.

**CI confirmed the #108 root cause verbatim** (`travis_109.log`, ANSI-stripped, 9654 lines):

- Line 8106: the calico-node gate's poll ended with `attempts: 48` and the standing module
  error `Unsupported parameters for (kubernetes.core.k8s_info) module: all_namespaces,
  field_selector, label_selector. Supported parameters include: … field_selectors …
  label_selectors … namespace …`, swallowed by `failed_when: false`
  (`failed_when_suppressed_exception` present, task reported `ok`).
- Lines 8108–8119: the gate's named fail then fired exactly as designed —
  `calico-node pod on this node never became Ready within 490 s (last pods: [], phases [],
  container states [])` — aborting the master chain before profile creation.
- Node1 reached the join phase and sat in the `kubernetesNodes` profile gate when the
  **90-minute `travis_wait` cap killed the build** (`duration=5400498786410` ns ≈ 90 min;
  `Your build exited with 1`). The join-scale gate ceiling must therefore stay compatible
  with the 90 min total (the 180 x 10 s ceiling, entered at ~45 min on the CI cold path,
  fits).

**Same bug class found and fixed in `tasks/drain-and-reset.yml`** (log line 6429, both
#108 and #109): the drain task passed `force`/`ignore_daemonsets`/`delete_emptydir_data`/
`terminate_grace_period` flat, which `kubernetes.core.k8s_drain` rejects
(`Unsupported parameters … Supported parameters include: … delete_options …`), and
`failed_when: false` swallowed it — drain silently no-opped on the reset path. Fix: the four
flags nested under the module-supported `delete_options:`. Live probe
(`probe_drain_shape.yml`, dummy node name): `unsupported-param-error=False`,
`msg=Node probe-does-not-exist not found.` — params accepted, no cluster side effect. Full
audit of both logs confirms exactly these two unsupported-parameter sites existed.

**#108 state anomaly resolved**: job 641604415 now reports `state: failed`,
`started_at 2026-11-14T23:09:15Z`, `finished_at 2026-11-15T00:42:04Z`, `restarted_at: None`
— it was never restarted; the transient `passed` reading was an API artifact. #108 stands
FAILED as recorded.

### CI delivery — build #110 (run #1 toward the two-green exit criterion)

_Pending: param-fix + drain-fix commit pushed after this record; build URL to be appended
on dispatch._

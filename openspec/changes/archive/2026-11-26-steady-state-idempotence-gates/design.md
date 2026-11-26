# Design: Steady-State Idempotence Gates

## Context

See `proposal.md` — Why. The technical situation that shapes the design:

- Renewal runs **out-of-band**: a per-host systemd timer (`kube-cert-renew.timer`,
  daily) replaces certificates in place (same key, same subject, new `notAfter`) via
  `ipa cert-request`. Converge therefore cannot distinguish "cert is current" from
  "cert is 29 days from expiry" by issuer or file presence alone — only the issuer
  check exists today.
- The timer's eligibility rule is "remaining validity < 30 days" (hardcoded in
  `templates/kube-cert-renew.sh.j2`); the converge-side check in
  `tasks/certs/ipa-cert-renewal.yml` uses the same 30-day window, hardcoded
  separately. A third copy would appear if gates re-implement it.
- Existing idiom: `ipa-controller-manager-client.yml` and `ipa-scheduler-client.yml`
  already gate issuance on the live cert's issuer via `openssl x509 -issuer` against
  the expected IPA CA, registering `*_swap_needed`. The design extends this idiom
  rather than inventing a new one.
- The `mv + mv back` static-pod restart (controller-manager/scheduler) and the
  `crictl stop` kubelet restart are inherently change-producing operations; the gate
  decides *whether* they run, their mechanics stay untouched (reversibility trumps
  purity here).
- `tasks/certs/ipa-ca-ensure.yml` already reports truthfully via stdout markers
  (`SERVICECAT-SET`, `CA-ACL-ADDED` emitted only on real writes); this is the
  convention A extends.

## Goals / Non-Goals

**Goals**
- One shared, reusable gate primitive for "does this on-disk IPA cert need
  re-issuance", used by every cert task and consistent with the timer.
- Truthful `changed` semantics everywhere in scope, per loop item.
- Converge remains the repair path: every gate must fail *open* (i.e., trigger the
  work) whenever the cluster deviates from desired end-state, so a failed timer
  never leaves a silently stale cluster.

**Non-Goals**
- No changes to `tasks/delete.yml` / `drain-and-reset.yml` / `prereq.yml` (reset
  flows are intentional churn).
- No changes to Calico recovery (already a no-op when Ready), static-pod restart
  mechanics, `kubectl get nodes` verification task, or the readiness gates.
- No per-leaf CRL revocation check in converge (see Decision 5).

## Decisions

### 1. Shared gate include `tasks/certs/_cert_swap_decision.yml`

A parameterized include (input: `cert_path`, `expected_issuer_glob`, register prefix;
output: `<prefix>_swap_needed` bool + `<prefix>_cert_info`) evaluating three read-only
checks:

1. **Issuer gate** — `openssl x509 -in <crt> -noout -issuer | grep -q "<expected issuer>"`
   (same as today's inline checks; `community.crypto.x509_certificate_info` is the
   native alternative but the repo's established, working idiom is openssl CLI with
   the shell-exception comment; the include centralizes it to one commented site).
2. **Validity gate** — parse `not_after` with `community.crypto.x509_certificate_info`
   and compare against `now + kube_cert_renewal_threshold_days` via Jinja
   (`now()` arithmetic), matching the timer's `openssl x509 -checkend` semantics.
3. **CA gate** — the IPA CA cert's `not_after` beyond the same threshold.

Why an include and not per-file inline: five cert files + admin-user + pki-swap would
otherwise copy the same 20-line check seven times; the repo already uses `_probe-*` /
`_krb_ticket` shared-include conventions. Alternative considered: a check-mode
`ipacert` — no such mode exists. Alternative: a module — overkill, and `community.crypto`
has no chain/expiry-policy module.

The include never writes markers to disk; state is always derived from live reads
(certificate bytes, cluster state), so gates replay on expiry, CA rotation, or foreign
re-issuance.

### 2. Threshold single-sourcing

New default `kube_cert_renewal_threshold_days: 30` in `defaults/main.yml`.
Templated into `kube-cert-renew.sh.j2` (replacing the hardcoded `-days 30` and
`-checkend` computation) and consumed by `_cert_swap_decision.yml` and the CA ACL
re-assert. Rationale: converge and timer MUST NOT disagree about "due" — a divergent
pair produces either churn (converge stricter than timer) or silent staleness (timer
stricter than converge).

### 3. Marker-based truthful `changed_when` (option A)

Extend `scripts/ipa-ca-ensure.sh` so the `ca-set-service-category` step echoes
`SERVICECAT-SET` only when the CLI reports an actual set, and the `ca-add-profile`
step echoes `CA-PROFILE-ADDED` on the same convention; task-level
`changed_when: "'SERVICECAT-SET' in stdout or 'CA-ACL-ADDED' in stdout or ..."`.
For `ipa_ca` parameter-idempotent sets (profile rules, `ca_enable`, delivery
methods): gate the task on a prior `ipa ca-show` read (delegated to idm, reusing
`tasks/_krb_ticket.yml`) and run the set only when a value differs. Alternatives:
`ipainstance`/`ipadeploy` modules don't cover CA config; native modules don't exist
for these IPA CLI verbs.

### 4. Gate placement per offender

| Site | Gate | Why safe |
|---|---|---|
| `admin-user.yml` re-embed | `slurp` `/var/lib/kube-clusteradm.crt` → compare base64 against the `client-certificate-data` value parsed from `admin.conf` (read back with a read-only `awk`/`yq`-free `shell` or `regex_replace` capture); re-embed only on mismatch | If an operator hand-edit removed the cert block, the comparison fails → repair runs (end-state is desired state, not "file untouched") |
| controller-manager / scheduler | `_cert_swap_decision.yml` for issuance; separate gate for the manifest move: read manifest `client-certificate-data`, compare with embedded crt; move only on mismatch. If the manifest file is missing entirely, treat as mismatch → move runs (repair) | Missing manifest = broken static pod = must restore, not skip |
| `ipa-pki-swap.yml` bundle replace | Build rendered bundle in memory (`slurp` both CAs, `copy: content:` to `/etc/kubernetes/pki/ca-bundle.crt`) — `copy` is content-idempotent, reports ok when bytes match. Drop the separate "CA changed?" shell gate; the `copy` module IS the gate | Content-equality by construction, no marker |
| `ipa-pki-swap.yml` manifest moves | Run when the bundle copy reported changed **or** a post-swap end-state check fails (manifest lacks the 2-CA material). Read manifests via `kubernetes.core.k8s` check_mode? No — static pods are plain files, not k8s objects: use `stat` + `slurp` + grep for the expected bundle fingerprint. Restores externally-deleted/mutated manifests | Repair path explicit |
| `persistent-volume.yml` | `kubernetes.core.k8s_info` (delegate_to master, `src: kubeconfig_admin_v1`) → skip absent+apply when the PV exists and rendered spec fields match (server, path, capacity, accessModes, storageClassName); delete+apply on drift; remove `failed_when: false` from the apply | k8s_info is read-only; `pv.spec.nfs` is immutable in-cluster, so drift requires the delete+recreate we already have |
| CA ACL re-assert loop | `ipa ca-show kubernetes-ca` (delegated, via `_krb_ticket.yml`) → `when: required_host not in shown_host_list` per item | Read-only check; add only when missing |
| `ca_enable` / delivery methods / profile rules | ca-show read → set only differing values | Same |

### 5. Revocation depth: v1 accepts CA-level checks, no per-leaf CRL

`openssl verify -crl_check` against the IPA CA chain requires fetching the CRL
distribution point (`ipa cert-show --pretty` AIA or the IPA `ca_cacert` CRL via
`ipa ca-show`/`get` over HTTP), which adds an idm round-trip + HTTP retrieval per
gate evaluation, and FreeIPA's CRL publication cadence (default 3h) can produce
false negatives and stale-CRL false positives on reconverge. Decision: v1 gates check
issuer + validity + CA validity + CA enabled-state (`ipa ca-show` `ipacaenabled`,
delegated to idm); per-leaf revocation remains the timer's and the operator's
concern. Revisit if a revocation incident demands it (listed in Risks).
Alternative rejected for v1: full `-crl_check` with `crldp` fetch.

### 6. `kubeclusteradm` keytab generation gate

Gate the `ktadd` on a read-only `kadmin.local -q "getent principals <princ>"` +
`stat` of the keytab plus (cheap) verification that the keytab actually
authenticates: attempt a `krb_ticket` acquisition from the keytab into a scratch
cache (the pattern in `tasks/certs/_probe-kubeclusteradm-keytab.yml`) → only
regenerate/export on failure or missing file. Reusing the existing probe include
rather than duplicating the logic.

## Risks / Trade-offs

- [Gate says "current" but the cert was revoked] → Accepted for v1 (Decision 5):
  CA enabled-state is checked; per-leaf revocation is the timer/operator path.
  Documented in the spec's repair-path requirement as an explicit gap.
- [Marker convention drift: someone adds a new step to `ipa-ca-ensure.sh` without a
  marker] → The `changed_when` string-match would silently report ok. Mitigation:
  keep the script's marker set documented in its header comment; the steady-state
  reconverge verification (task group 7) catches always-changed, not
  never-changed — call this out in review.
- [Jinja date comparisons on `not_after` vs the timer's `-checkend` differ at
  boundaries] → Both use the same threshold default; boundary disagreement of hours
  is harmless (next tick or next converge fixes it).
- [`k8s_info` field comparison misses PV drift (e.g. `claimRef` hijack)] → Compare
  the documented field set (server/path/capacity/accessModes/storageClass); claimRef
  drift is out of scope and rare; noted as a limitation, not a blocker.
- [Manifest-grep gate fingerprints on bundle content that rotates] → The gate
  compares against the *rendered* bundle bytes each run, never a saved copy, so CA
  rotation flips it to "move" automatically.

## Migration Plan

Pure converge-path refactor: deploy = run converge once (first post-change converge
will legitimately report the true "state was wrong" changes), then reconverge to
confirm zero-change. Rollback = `git revert` the role commits; no persistent state
is introduced (no new files on managed hosts except `/etc/kubernetes/pki/ca-bundle.crt`
content, which is what converge already writes).

## Open Questions

- Whether `admin-user.yml`'s admin.conf read-back should parse YAML
  (`from_yaml`) or regex the base64 line — implementation detail, decide at apply
  time based on kubeconfig formatting.

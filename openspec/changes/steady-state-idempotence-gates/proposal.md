# Proposal: steady-state-idempotence-gates

## Why

A steady-state reconverge of this role (cluster already built, certificates valid, CRBs
provisioned) currently rewrites large amounts of unchanged state: the kubeconfig client
certificate is re-enrolled and re-embedded on every run, the PKI swap re-copies the CA
bundle and re-moves every static-pod manifest (forcing unnecessary API server / etcd
restarts), the CA ACL loop and service-category gate report spurious changes, and the NFS
PersistentVolume is deleted and recreated on every converge — opening a delete/apply crash
window in which the PV simply does not exist. Beyond noisy diffs that hide real drift, the
PV churn is a availability risk and the blanket `changed_when: false` / `failed_when: false`
suppressions used across these paths violate the monorepo idempotency rule (tasks must be
idempotent by construction or gated on a read-only check; masking is reserved for strictly
read-only commands).

## What Changes

- Add a shared certificate decision include `tasks/certs/_cert_swap_decision.yml` that
  computes, for one on-disk certificate, whether issuance is needed: issuer gate (not
  signed by the expected IPA CA), validity gate (`not_after` within a new
  `kube_cert_renewal_threshold_days`, default 30 — the same threshold the renewal timer
  uses), and CA gate (sub-CA `not_after` within threshold, or sub-CA disabled). All checks
  are read-only; issuance and deployment replay when a certificate approaches expiry or
  the CA requires re-issuance, so converge remains a repair path for a failed timer.
- Gate `tasks/certs/ipa-controller-manager-client.yml` and `tasks/certs/ipa-scheduler-client.yml`
  on the shared decision (replacing the current issuer-only `*_swap_needed` gate), and
  split the manifest move into its own gate: it runs only when the manifest's embedded
  `client-certificate-data` differs from the on-disk certificate.
- Gate `tasks/admin-user.yml`: re-embed `admin.conf`'s `client-certificate-data` only when
  its content differs from the current valid `/var/lib/kube-clusteradm.crt`; the enrollment
  block runs only when the certificate is absent, invalid (issuer/validity gate), or the
  CRB was missing.
- Gate `tasks/certs/ipa-pki-swap.yml`: the bundle replace task runs only when the staged
  bundle bytes differ from `/etc/kubernetes/pki/ca-bundle.crt`; the manifest move runs only
  when the bundle changed this run **or** the post-swap end-state check fails (so converge
  still repairs a manifest reverted to the kubeadm CA). The `openssl verify` chain gate and
  the KCM-lease / scheduler-Ready / kubectl verification gates stay unconditional — they are
  read-only, self-healing evidence.
- Truthful change reporting for provisioning loops: the service-category gate and the CA ACL
  add loop report a real change instead of blanket `changed_when: false`, using the
  `SERVICECAT-SET` / `CA-ACL-ADDED` stdout-marker convention already established by
  `tasks/certs/ipa-ca-ensure.yml`.
- PersistentVolume idempotency in `tasks/persistent-volume.yml`: read the live PV with
  `kubernetes.core.k8s_info` and skip delete/recreate when it exists and its NFS
  server/path match the desired spec; remove `failed_when: false` from the `kubectl apply`
  so genuine apply failures fail the converge.
- Template the renewal threshold into `templates/kube-cert-renew.sh.j2` from
  `kube_cert_renewal_threshold_days` so the converge-time gates and the systemd timer can
  never drift apart.

## Non-goals

- Reset/delete-path idempotence: `kubeadm reset`, `swapoff --all`, `pkill haproxy`, and the
  `reset: true` flows stay as-is — they are explicitly destructive by design.
- Calico recovery flow: already a no-op when nodes are Ready (the ready-gate skips the
  entire block); the `mv` + `mv`-back static-pod restart mechanics are unchanged, only
  whether the move runs is gated.
- Per-leaf CRL revocation checks in the converge-time gate (stays the timer's responsibility;
  accepted gap documented in design).
- No new scenarios, hosts, CAs, or topology changes; no change to the Kerberos ticketing
  patterns (`_krb_ticket.yml` stays the single acquisition entry point).

## Capabilities

### New Capabilities
- `steady-state-idempotence`: Converge on an already-built, healthy cluster is a
  no-change operation — certificate issuance/swap, CA ACL grants, service-category writes,
  PKI bundle replacement, static-pod manifest moves, and PV (re)creation are each gated on
  a read-only check of actual desired-vs-actual state, and every task's `changed` status
  reflects a real state mutation.

### Modified Capabilities
- `kube-cert-renewal`: The renewal threshold becomes a single role default
  (`kube_cert_renewal_threshold_days`) shared by the converge-time issuance gates and the
  templated systemd-timer script; converged gates replay issuance when a certificate or
  sub-CA approaches expiry (no permanent skip).
- `pv-nfs-kind`: The PV apply task becomes conditional on the live PV's absence or spec
  drift (read via `k8s_info`), and apply failures are no longer swallowed by
  `failed_when: false`.

## Impact

- Affected files: `tasks/certs/_cert_swap_decision.yml` (new), `tasks/certs/ipa-controller-manager-client.yml`,
  `tasks/certs/ipa-scheduler-client.yml`, `tasks/certs/ipa-pki-swap.yml`, `tasks/certs/ipa-cert-renewal.yml`
  (CA ACL loop change-reporting), `tasks/admin-user.yml`, `tasks/persistent-volume.yml`,
  `tasks/certs/ipa-ca-ensure.yml` (marker convention reference only), `templates/kube-cert-renew.sh.j2`,
  `defaults/main.yml` (new threshold default).
- Proof gate: the full molecule cycle on the host-OS-matched scenario
  (`destroy → converge-monorepo → verify-monorepo`) **plus a second reconverge**; the
  acceptance criterion is a near-zero-change task list on the reconverge with all `verify`
  gates green (all nodes Ready, per-pod evidence, PV mounts).
- No breaking changes for consumers: no variable renames, no task-file removals; role
  defaults gain one new optional variable with a default matching current behavior.

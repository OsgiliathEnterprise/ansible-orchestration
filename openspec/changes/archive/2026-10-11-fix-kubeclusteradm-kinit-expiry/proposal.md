## Why

Converge of `tcharl.ansible_orchestration` fails on fresh VMs at the task
"Ipa-kube-admin-credential | verify kubeclusteradm can authenticate via kinit" with:

```
Password for kubeclusteradm@OSGILIATH.TEST:
Password expired.  You must change it now.
Enter new password:
kinit: Cannot read password while getting initial credentials
```

Root cause (verified empirically on the scenario's IPA server, FreeIPA 4.13.4):
passwords set through the API/CLI by an administrator are stored with
`krbPasswordExpiration` equal to the time they were set — i.e. immediately
expired. The KDC rejects such accounts (`PW_EXPIRED`) until the user performs a
self-service password change once, which recomputes expiration to
now + maxpwage (90 days). Because `ipauser` uses `update_password: on_create`,
the failure persists across re-converges until someone manually activates the
account.

A second, independent failure was observed on re-converged masters at the
"Admin-user | enroll CSR" task:

```
invalid 'csr': subject alt name type DNSName is forbidden for user principals
```

Root cause: `community.crypto.openssl_csr` defaults to
`use_common_name_for_san: true`, which adds a `DNS:` SAN to the CSR; FreeIPA
rejects DNS-type SANs on *user* principals. The module reuses an existing CSR
file even when it no longer matches its parameters, so a CSR generated before
the fix keeps failing every re-converge.

The original fix for the kinit failure (a three-line stdin kinit forced-change
flow) proved fragile in live testing: a freshly created account is both
immediately expired and inside the KDC's 1-hour min-password-age window
("Too soon"), so it cannot activate itself through the KDC changepw path, and
the stored-key state after the flow was observed to be unreliable.

## What Changes

- **Kinit fix, revised design (validated live):** create the `kubeclusteradm`
  IPA user *without* a password (no immediate-expiration attribute, no
  min-age window). Set its Kerberos key with `kadmin.local cpw` on the IPA
  server (root, local KDB) — no KDC changepw policy, no "Too soon" rejection,
  and the KDC computes expiration as last-change + maxpwage (90 days), so the
  account is immediately usable. A one-line `kinit` probe gates the `cpw`
  task: steady state (probe succeeds) is a no-op; a missing key (fresh
  account), wrong key (owner changed it), or expired credential re-sets the
  key to the role-managed value. The one-line kinit verification and
  `kubectl get nodes` checks are unchanged.
- **CSR fix:** set `use_common_name_for_san: false` on the `openssl_csr` task
  so the CSR carries only the CN (no DNS SAN, which FreeIPA rejects for user
  principals), and remove a legacy SAN-bearing CSR (and its paired key) before
  regeneration so re-converged masters do not re-submit a CSR the module
  would reuse as-is.
- **Ordering:** the user-creation task moves into
  `ipa-kube-admin-credential.yml` (which runs before `admin-user.yml`), with
  the `email` attribute required by ipacert validation. `admin-user.yml`
  keeps CSR generation, enrollment, and the admin.conf patch.
- Report change status truthfully: the `cpw` task is gated on the probe
  (skipped in steady state); the probe and verification tasks are
  cache/read-only checks (`changed_when: false`, consistent with the existing
  kinit verification task).

## Capabilities

### Modified Capabilities

(none)

### New Capabilities

- `ipa-kube-admin-credential`: The orchestration role SHALL provision the
  `kubeclusteradm` IPA user such that it is Kerberos-authenticable via
  non-interactive `kinit` immediately after provisioning, on both fresh
  creation and re-converge, and SHALL enroll its admin client CSR (without a
  DNS SAN) under the kubernetes-ca CA.

## Impact

- `ansible/roles/tcharl.ansible_orchestration/tasks/ipa-kube-admin-credential.yml` — user creation without password, kinit probe, `kadmin.local cpw` task, header comment update
- `ansible/roles/tcharl.ansible_orchestration/tasks/admin-user.yml` — `use_common_name_for_san: false`, legacy CSR cleanup, user-creation task removed (moved)
- Verification: full molecule cycle (`destroy` → `converge-monorepo` → `verify-monorepo`, scenario `parallels`) plus a re-converge to confirm idempotent behavior

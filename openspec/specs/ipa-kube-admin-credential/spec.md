# IPA Kube Admin Credential

## Purpose

Define how the `kubeclusteradm` IPA service account is provisioned so that it is Kerberos-authenticable via non-interactive `kinit` immediately after provisioning — both on fresh creation and on re-converge — how its keytab becomes the steady-state credential, and how its admin client CSR is enrolled under the `kubernetes-ca` CA without a DNS SAN.

## Requirements

### Requirement: kubeclusteradm is Kerberos-authenticable immediately after provisioning
The role SHALL ensure the `kubeclusteradm` IPA user can obtain a Kerberos ticket via non-interactive `kinit`, both when the account is freshly created and on re-converge. Because FreeIPA stores API-set passwords with an immediate expiration (`krbPasswordExpiration` = set time) and the KDC rejects changepw within the min-password-age window after creation ("Too soon"), the role SHALL create the user without a password and set its Kerberos key with `kadmin.local cpw` on the IPA server, which bypasses the KDC changepw policy and stores no `krbPasswordExpiration` attribute (the KDC computes the expiration as last-change + maxpwage).

The steady-state credential SHALL be the keytab, not the password: `ipa-cert-renewal.yml` exports the renewal keytab with a **non-rotating** keytab export (see design D3 amendment). The export writes the current KDB key without rotating it: the principal key is unchanged by re-export (kvno stable), the managed password is not invalidated by keytab regeneration, and the keytab tracks the KDB — if the KDB key changes externally, the next regeneration writes the current key. The `cpw` task's `Too soon to change password` exposure therefore no longer arises from keytab export; the `cpw` gate (both credentials unusable) and the fresh-install password fallback are unchanged.

The probe and verification tasks SHALL run delegated to the IPA server (`become`, where the `kubeclusteradm` keytab lives at `/var/lib/kube-cert-renew/kubeclusteradm.keytab`, mode `0600` — a root-only unit-state location, not under `/tmp`), try the keytab first, and fall back to the managed password only on the fresh-install path (no keytab yet, before `ipa-cert-renewal.yml` runs).

#### Scenario: Fresh account without a key
- **WHEN** the role creates `kubeclusteradm` without a password and neither credential is usable (no keytab file yet, no key stored)
- **THEN** the probe reports the credential missing, the role runs `kadmin.local cpw` on the IPA server, and verification succeeds via the password branch (the keytab does not exist yet — it is generated later by `ipa-cert-renewal.yml`)

#### Scenario: Re-converge on an already-usable credential
- **WHEN** the keytab is usable (a native keytab probe — `krb_ticket` with `keytab: true` — succeeds on the IPA server)
- **THEN** the probe reports the keytab usable, the `cpw` task is skipped (no min-age-window exposure), verification succeeds via the keytab, and no account state is changed

#### Scenario: Managed password survives keytab export
- **WHEN** the role exports (or re-exports) the keytab during the renewal flow
- **THEN** the export fetches the current KDB key without rotating it, the managed password remains usable, and both credential paths (keytab and password) stay available — the password fallback is a live recovery path, not a dead letter

#### Scenario: Credential rotated or changed after provisioning
- **WHEN** the keytab is stale (the KDB key rotated out from under it) or the password was changed or expired by an owner
- **THEN** the probe reports the credential missing (both credentials unusable), the `cpw` task re-asserts the role-managed value, verification succeeds via the password branch, and the keytab task (gated on keytab usability, not file presence) regenerates the keytab — restoring a consistent steady state

#### Scenario: Keytab never lands in /tmp
- **WHEN** the renewal flow exports the keytab on the IPA server
- **THEN** the keytab is written directly to `/var/lib/kube-cert-renew/kubeclusteradm.keytab` with mode `0600`, and no intermediate copy of the keytab is created under `/tmp`

### Requirement: Key-setting task reports truthful change status and hard-fails on the min-age window
The `cpw` task SHALL run only when the probe reports both credentials unusable (skipped otherwise), so steady-state re-converges report no change and are never exposed to the KDC min-password-age window. If the KDC still rejects a re-assert within the window (kadmin prints "Too soon to change password" to stderr while exiting 0), the task SHALL fail loudly via `failed_when` instead of reporting a silent false success. The probe and verification tasks are ticket-cache-only (no persistent state) and SHALL use `changed_when: false`, consistent with the role's existing kinit verification pattern. Blanket `changed_when` suppression on mutating commands is NOT allowed.

#### Scenario: Fresh account key set
- **WHEN** the probe reports the credential missing and `kadmin.local cpw` runs
- **THEN** the task reports changed=true

#### Scenario: Already-usable account
- **WHEN** the probe reports a usable credential
- **THEN** the `cpw` task is skipped (skipped, not ok-with-change)

#### Scenario: Re-assert rejected by the min-age window
- **WHEN** `kadmin.local cpw` runs within the KDC min-password-age window after a key rotation
- **THEN** kadmin exits 0 with "Too soon to change password" on stderr and the task fails loudly via `failed_when`

### Requirement: Verification remains read-only after key setting
The verification task SHALL run after the `cpw` task and SHALL remain strictly read-only (`changed_when: false`), failing loudly if no credential authenticates. It tries the keytab first and falls back to the password (fresh-install path, where the `cpw` task just set the key). The cluster-API acceptance check (`kubectl --kubeconfig=/etc/kubernetes/admin.conf get nodes`) runs at the end of `admin-user.yml`, after the admin client cert is re-embedded into `admin.conf` — not in this file.

#### Scenario: Credential still unusable
- **WHEN** no credential authenticates after the `cpw` task
- **THEN** the verification task fails loudly and the converge stops

#### Scenario: Fresh-install verification
- **WHEN** the keytab does not exist yet (fresh converge, before `ipa-cert-renewal.yml`)
- **THEN** the verification task authenticates via the password branch set by the `cpw` task

### Requirement: Admin client CSR carries no DNS SAN
The role SHALL generate the admin CSR with `use_common_name_for_san: false` so it carries only the CN. FreeIPA rejects DNS-type SANs on user principals (`subject alt name type DNSName is forbidden for user principals`), and the CSR SHALL enroll successfully under the kubernetes-ca CA (`kubeAdministrators` profile).

#### Scenario: CSR generated on a master
- **WHEN** the CSR is generated for `kubeclusteradm`
- **THEN** it contains no `subjectAltName` extension and `ipacert` enrollment succeeds

#### Scenario: Re-converged master with a legacy SAN-bearing CSR
- **WHEN** a CSR file left on the master from before the `use_common_name_for_san: false` fix carries a `X509v3 Subject Alternative Name` extension
- **THEN** the role removes the legacy CSR and its paired key before regeneration, so the next `openssl_csr` run produces a SAN-free CSR instead of re-submitting the legacy one

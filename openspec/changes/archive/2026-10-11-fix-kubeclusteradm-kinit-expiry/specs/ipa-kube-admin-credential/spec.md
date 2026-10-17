## ADDED Requirements

### Requirement: kubeclusteradm is Kerberos-authenticable immediately after provisioning
The role SHALL ensure the `kubeclusteradm` IPA user can obtain a Kerberos ticket via non-interactive `kinit` on the K8s master, both when the account is freshly created and on re-converge. Because FreeIPA stores API-set passwords with an immediate expiration (`krbPasswordExpiration` = set time) and the KDC rejects changepw within the min-password-age window after creation, the role SHALL create the user without a password and set its Kerberos key with `kadmin.local cpw` on the IPA server, which bypasses the KDC changepw policy.

#### Scenario: Fresh account without a key
- **WHEN** the role creates `kubeclusteradm` without a password and the kinit probe fails (no key stored)
- **THEN** the role runs `kadmin.local cpw` on the IPA server, storing the key with no `krbPasswordExpiration` attribute (KDC computes expiration as last-change + maxpwage)
- **AND** a ticket cache entry for `kubeclusteradm` exists on the master after the verification task

#### Scenario: Re-converge on an already-usable credential
- **WHEN** `kubeclusteradm` already holds a usable, non-expired key
- **THEN** the kinit probe succeeds, the `cpw` task is skipped, and no account state is changed

#### Scenario: Credential changed or expired after provisioning
- **WHEN** the account's key no longer matches the role-managed value (owner change) or the password has expired (90+ days)
- **THEN** the kinit probe fails and the `cpw` task re-sets the role-managed value, restoring a usable credential

### Requirement: Key-setting task reports truthful change status
The `cpw` task SHALL run only when the probe reports the credential unusable (skipped otherwise), so steady-state re-converges report no change. The probe and the one-line kinit verification tasks are ticket-cache-only (no persistent state) and SHALL use `changed_when: false`, consistent with the role's existing kinit verification pattern. Blanket `changed_when` suppression on mutating commands is NOT allowed.

#### Scenario: Fresh account key set
- **WHEN** the probe fails and `kadmin.local cpw` runs
- **THEN** the task reports changed=true

#### Scenario: Already-usable account
- **WHEN** the probe succeeds
- **THEN** the `cpw` task is skipped (skipped, not ok-with-change)

### Requirement: Verification remains read-only after key setting
The one-line `kinit` verification task SHALL run after the `cpw` task and SHALL remain strictly read-only (`changed_when: false`), failing loudly if the credential is still unusable. The `kubectl --kubeconfig=/etc/kubernetes/admin.conf get nodes` check SHALL run after it.

#### Scenario: Key still unusable
- **WHEN** `kadmin.local cpw` fails (e.g. principal missing, wrong idm host)
- **THEN** the `cpw` task fails loudly and the verification task never masks the failure

### Requirement: Admin client CSR carries no DNS SAN
The role SHALL generate the admin CSR with `use_common_name_for_san: false` so it carries only the CN. FreeIPA rejects DNS-type SANs on user principals (`subject alt name type DNSName is forbidden for user principals`), and the CSR SHALL enroll successfully under the kubernetes-ca CA (`kubeAdministrators` profile).

#### Scenario: CSR generated on a master
- **WHEN** the CSR is generated for `kubeclusteradm`
- **THEN** it contains no `subjectAltName` extension and `ipacert` enrollment succeeds

#### Scenario: Re-converged master with a legacy SAN-bearing CSR
- **WHEN** a CSR file left on the master from before the `use_common_name_for_san: false` fix carries a `X509v3 Subject Alternative Name` extension
- **THEN** the role removes the legacy CSR and its paired key before regeneration, so the next `openssl_csr` run produces a SAN-free CSR instead of re-submitting the legacy one

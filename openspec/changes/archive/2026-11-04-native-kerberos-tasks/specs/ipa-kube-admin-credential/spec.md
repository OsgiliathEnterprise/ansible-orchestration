## MODIFIED Requirements

### Requirement: kubeclusteradm is Kerberos-authenticable immediately after provisioning
The role SHALL ensure the `kubeclusteradm` IPA user can obtain a Kerberos ticket via non-interactive `kinit`, both when the account is freshly created and on re-converge. Because FreeIPA stores API-set passwords with an immediate expiration (`krbPasswordExpiration` = set time) and the KDC rejects changepw within the min-password-age window after creation ("Too soon"), the role SHALL create the user without a password and set its Kerberos key with `kadmin.local cpw` on the IPA server, which bypasses the KDC changepw policy and stores no `krbPasswordExpiration` attribute (the KDC computes the expiration as last-change + maxpwage).

The steady-state credential SHALL be the keytab, not the password: `ipa-cert-renewal.yml` exports the renewal keytab with a **non-rotating** keytab export (`kadmin.local ktadd -norandkey` on the IPA master — the documented shell exception replacing the native-module plan, whose only non-rotating mode `--retrieve` is refused by FreeIPA's `krbPrincipalKey` search-only ACI; see design D3 amendment). The export writes the current KDB key without rotating it: the principal key is unchanged by re-export, the managed password is not invalidated by keytab regeneration, and the keytab tracks the KDB — if the KDB key changes externally, the next regeneration writes the current key. The `cpw` task's `Too soon to change password` exposure therefore no longer arises from keytab export; the `cpw` gate (both credentials unusable) and the fresh-install password fallback are unchanged.

The probe and verification tasks SHALL run delegated to the IPA server (`become`, where `/tmp/kubeclusteradm.keytab` lives), try the keytab first, and fall back to the managed password only on the fresh-install path (no keytab yet, before `ipa-cert-renewal.yml` runs).

#### Scenario: Fresh account without a key
- **WHEN** the role creates `kubeclusteradm` without a password and neither credential is usable (no keytab file yet, no key stored)
- **THEN** the probe reports the credential missing, the role runs `kadmin.local cpw` on the IPA server, and verification succeeds via the password branch (the keytab does not exist yet — it is generated later by `ipa-cert-renewal.yml`)

#### Scenario: Re-converge on an already-usable credential
- **WHEN** the keytab is usable (a `kinit -kt` on the IPA server succeeds)
- **THEN** the probe reports the keytab usable, the `cpw` task is skipped (no min-age-window exposure), verification succeeds via the keytab, and no account state is changed

#### Scenario: Managed password survives keytab export
- **WHEN** the role exports (or re-exports) the keytab during the renewal flow
- **THEN** the export fetches the current KDB key without rotating it, the managed password remains usable, and both credential paths (keytab and password) stay available — the password fallback is a live recovery path, not a dead letter

#### Scenario: Credential rotated or changed after provisioning
- **WHEN** the keytab is stale (the KDB key rotated out from under it) or the password was changed or expired by an owner
- **THEN** the probe reports the credential missing (both credentials unusable), the `cpw` task re-asserts the role-managed value, verification succeeds via the password branch, and the keytab task (gated on keytab usability, not file presence) regenerates the keytab — restoring a consistent steady state

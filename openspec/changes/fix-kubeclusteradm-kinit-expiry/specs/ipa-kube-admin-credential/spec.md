## ADDED Requirements

### Requirement: kubeclusteradm is Kerberos-authenticable immediately after provisioning
The role SHALL ensure the `kubeclusteradm` IPA user can obtain a Kerberos ticket via non-interactive `kinit` on the K8s master, both when the account is freshly created and on re-converge. Because FreeIPA stores API-set passwords with an immediate expiration (`krbPasswordExpiration` = set time), the role SHALL activate such accounts through kinit's forced-change flow before verification.

#### Scenario: Fresh account with API-set password
- **WHEN** the role creates `kubeclusteradm` and its KDC-reported password is expired
- **THEN** a self-service password change is performed via kinit's "Enter new password" flow using the same credential value (old + new + confirm)
- **AND** the account's password expiration is recomputed by the KDC to now + maxpwage
- **AND** a ticket cache entry for `kubeclusteradm` exists on the master

#### Scenario: Re-converge on an already-active account
- **WHEN** `kubeclusteradm` already holds a non-expired password
- **THEN** activation consumes only the initial kinit attempt, reports no state change, and leaves the credential value untouched

### Requirement: Activation task reports truthful change status
The activation task SHALL report `changed` only when it actually performed a self-service password change, keyed on an observable stdout marker. Blanket `changed_when` suppression is NOT allowed because the command mutates persistent state (password expiration) in the fresh-account case.

#### Scenario: Fresh account activated
- **WHEN** the forced-change flow runs and succeeds
- **THEN** the task reports changed=true

#### Scenario: Already-active account
- **WHEN** the initial one-line kinit succeeds without a password change
- **THEN** the task reports changed=false (ok)

### Requirement: Verification remains read-only after activation
The existing one-line `kinit` verification task SHALL run after activation and SHALL remain strictly read-only (`changed_when: false`), failing loudly if the credential is wrong or still expired.

#### Scenario: Wrong password
- **WHEN** the stored credential does not match the account's password
- **THEN** both the activation retry and the verification task fail with kinit's authentication error, so a misconfiguration cannot be masked by the activation fallback

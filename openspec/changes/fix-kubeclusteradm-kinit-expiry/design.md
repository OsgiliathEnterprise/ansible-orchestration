## Context

`tasks/ipa-kube-admin-credential.yml` (runs on the K8s master, gated by
`kube_masters_group`) creates the `kubeclusteradm` IPA user via
`freeipa.ansible_freeipa.ipauser` (`update_password: on_create`, password from
`vault_kube_admin_password | default('KubeClusterAdm!2026')`), then verifies
non-interactive kinit with a one-line stdin pipe, then checks the cluster API
with `kubectl get nodes`.

On fresh VMs the verification task fails: `kinit` reports "Password expired.
You must change it now." and cannot read a new password from the single-line
stdin.

### Root cause (empirical evidence)

Tested directly on the scenario's IPA server (`idm.osgiliath.test`, FreeIPA
4.13.4, global policy: max lifetime 90 days, min lifetime 1 hour, history 0):

- `ipa user-add --password` and admin `ipa passwd` both store
  `krbPasswordExpiration` = the time the password was set (verified on two
  users, three settings). The KDC therefore answers `PW_EXPIRED`.
- A self-service change performed through kinit's forced-change flow — piping
  three lines (old + new + confirm) where new equals the current value — is
  accepted even within the 1-hour min-lifetime window (forced changes are not
  subject to it), recomputes `krbPasswordExpiration` to now + 90 days, and
  issues a ticket. Subsequent one-line kinit then succeeds.

Note: kinit's expired-password flow consumes exactly three stdin lines
(password, new password, confirmation). Two lines are not enough ("Cannot read
password while getting initial credentials").

## Goals / Non-Goals

**Goals:**
- Make fresh-account converge deterministic: no manual intervention needed to activate `kubeclusteradm`
- Keep the stored credential value unchanged (the same password keeps working for kinit and any other consumer)
- Truthful change reporting on re-converge (no blanket `changed_when` suppression)

**Non-Goals:**
- Changing the realm-wide FreeIPA password policy
- Switching to a different credential mechanism (e.g. keytab) — out of scope; the role's contract is "password doubles as Kerberos password"

## Decisions

1. **Self-service activation via kinit's forced-change flow** (chosen). A new task between user creation and verification runs:
   ```bash
   set -o pipefail
   if echo "$PW" | kinit $USER 2>/dev/null; then
     echo "already-active"
   else
     printf '%s\n%s\n%s\n' "$PW" "$PW" "$PW" | kinit $USER || exit 1
     echo "activated"
   fi
   ```
   - Fresh/expired account: first attempt fails, second performs the self-service change (same value) and obtains a ticket → stdout `activated`.
   - Active account: first attempt succeeds; only one stdin line is consumed → stdout `already-active`, no state change.
   - Wrong password: both attempts fail → task fails with kinit's error message (first attempt's stderr suppressed as the expected path).
   - `changed_when: "'activated' in stdout"` — truthful, per repo idempotency rules (no blanket suppression; the command is not read-only when it activates).

2. **Rejected: direct LDAP modification of `krbPasswordExpiration`** (e.g. via dirman credentials). Bypasses IPA's policy computation (would have to hardcode now+90d), requires raw-credential handling, and leaves `krblastpwdchange` inconsistent with the KDC's view.

3. **Rejected: realm-wide password policy change (`maxpwage=0`).** Changes security posture for every account in the environment; also does not address the admin-set-expiration behavior itself.

4. **Rejected: interactive/TTY kinit.** Not scriptable in molecule CI; the three-line stdin flow is the non-interactive equivalent of answering the "Enter new password" prompt.

5. **`update_password: on_create` stays as-is.** Re-converge must not reset the password (resetting would re-expire it and churn `krblastpwdchange`). Activation is a no-op state-wise on already-active accounts, so idempotence holds.

## Risks / Mitigations

- **Min-lifetime policy (1 hour):** only blocks voluntary changes; forced expired-password changes are exempt — verified empirically (activation succeeded ~3 minutes after the admin set the password).
- **Password history:** global history size is 0, so re-setting the same value is not rejected. If a future environment enables history, activation of an *expired* password to its own value could be blocked; acceptable for this scenario's fixed policy.
- **Stdin contract:** relies on kinit reading exactly three lines in the expired flow (verified against krb5 1.20+ behavior in the scenario). The `|| exit 1` guard ensures a failed second attempt cannot be masked by the trailing `echo`.

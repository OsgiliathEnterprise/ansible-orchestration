## Context

`tasks/ipa-kube-admin-credential.yml` (runs on the K8s master, gated by
`kube_masters_group`) creates the `kubeclusteradm` IPA user, then verifies
non-interactive kinit, then checks the cluster API with `kubectl get nodes`.
It runs *before* `admin-user.yml` (CSR generation + `ipacert` enrollment), so
the user must exist at this point: the enrollment resolves the principal from
the CSR's `CN`, which must match the user's login.

On fresh VMs the kinit verification task failed: `kinit` reports "Password
expired. You must change it now." and cannot read a new password from a
single-line stdin.

### Root cause (empirical evidence)

Tested directly on the scenario's IPA server (`idm.osgiliath.test`, FreeIPA
4.13.4, global policy: max lifetime 90 days, min lifetime 1 hour, history 0):

- `ipa user-add --password` and admin `ipa passwd` both store
  `krbPasswordExpiration` = the time the password was set (verified on two
  users, three settings). The KDC therefore answers `PW_EXPIRED`.
- The only KDC-side fix is a self-service changepw — but right after creation
  the account is inside the 1-hour min-password-age window, so the KDC answers
  "Password cannot be changed: Too soon since last password change". A fresh
  account therefore cannot activate itself through the KDC changepw path.
- `kadmin.local` (root on the IPA server, local KDB) is NOT subject to the
  KDC changepw policy: `cpw` on a fresh account succeeds, stores the key with
  `krblastpwdchange` = now and **no** `krbPasswordExpiration` attribute, so
  the KDC computes expiration as last-change + maxpwage (90 days) — in the
  future. A subsequent one-line `kinit` succeeds with a clean (non-expired)
  TGT, and `kubectl get nodes` with the admin.conf client certificate passes.

### Secondary root cause (CSR)

`community.crypto.openssl_csr` defaults to `use_common_name_for_san: true`,
adding a `DNS:<commonName>` SAN. FreeIPA rejects DNS-type SANs on user
principals (`subject alt name type DNSName is forbidden for user principals`)
at `ipacert` enrollment. The module also reuses an existing CSR file even when
it no longer matches its parameters, so a CSR generated before the fix keeps
failing every re-converge on a master that still holds it.

## Goals / Non-Goals

**Goals:**
- Make fresh-account converge deterministic: no manual intervention needed to make `kubeclusteradm` Kerberos-authenticable
- Keep the stored credential value unchanged (the same password keeps working for kinit and any other consumer)
- Truthful change reporting on re-converge (no blanket `changed_when` suppression on mutating tasks)
- Make CSR enrollment deterministic on fresh and re-provisioned masters (no DNS SAN)

**Non-Goals:**
- Changing the realm-wide FreeIPA password policy
- Switching to a different credential mechanism (e.g. keytab) — out of scope; the role's contract is "password doubles as Kerberos password"

## Decisions

1. **Create the user without a password; set the key via `kadmin.local cpw` on the IPA server** (chosen, validated live). Tasks in `ipa-kube-admin-credential.yml`:
   - `ipauser` with `state: present`, `first`/`last`/`email`, and **no** password parameter (`update_password: on_create` kept for the module's attribute-comparison behavior on re-converge). A fresh account therefore has no `krbPasswordExpiration` attribute at all — nothing is immediately expired, and there is no min-age window to trip.
   - **Probe**: one-line `kinit` (password piped via stdin, `changed_when: false` — ticket-cache only, no persistent state, consistent with the existing verification task). Prints `usable` or `missing`. Fresh account (no key), wrong key, or expired credential all fail the probe.
   - **`cpw`**: `kadmin.local -q "cpw <principal>"` with the password piped via stdin (two lines: new + confirm), delegated to `{{ groups[idm_group] | first }}` with `become: true`, gated `when: "'missing' in probe.stdout"`. `kadmin.local` runs as root against the local KDB: no KDC changepw policy, no "Too soon" rejection, no expiry attribute stored.
   - Verification tasks (one-line `kinit`, `kubectl get nodes`) unchanged.
   - Idempotency: steady state → probe `usable` → `cpw` skipped → all tasks report ok. The `cpw` task mutates persistent state only when the credential is actually unusable, and is then a required repair, not churn.
   - Self-healing: if the owner changes the password or the 90-day expiration lapses, the probe fails and the `cpw` task re-sets the role-managed value.

2. **Rejected (superseded): self-service activation via kinit's forced-change flow** (the original implementation of this change). Three-line stdin (old + new + confirm) driving kinit's expired-password flow. Empirically fragile: (a) a fresh account is inside the KDC min-password-age window ("Too soon"), so the flow's changepw is rejected and the account stays unusable; (b) the stored-key state after the flow was observed to be unreliable (subsequent one-line kinit with the same value failed preauthentication); (c) it depends on kinit's exact stdin prompt sequence, which is version-sensitive. The `kadmin.local` path removes all three failure modes.

3. **Rejected: direct LDAP modification of `krbPasswordExpiration`** (e.g. via dirman credentials). Bypasses IPA's policy computation (would have to hardcode now+90d), requires raw-credential handling, and leaves `krblastpwdchange` inconsistent with the KDC's view.

4. **Rejected: realm-wide password policy change (`maxpwage=0`).** Changes security posture for every account in the environment; also does not address the admin-set-expiration behavior itself.

5. **Rejected: interactive/TTY kinit.** Not scriptable in molecule CI.

6. **CSR without DNS SAN + legacy cleanup.** `openssl_csr` gets `use_common_name_for_san: false` (the CSR DN carries `CN=<login>` — FreeIPA requires the CSR's `commonName` to match the user's login for user principals — and no SAN at all). Before regeneration, a read-only `openssl req -text` inspection detects a legacy SAN (`X509v3 Subject Alternative Name` section) and a `file: state: absent` task removes the CSR and its paired key so the next `openssl_csr` run generates a clean CSR. The CSR file is PEM (base64-encoded DER): neither the raw file content nor its `b64decode` contains the human-readable extension name, so a `slurp`-based grep can never detect the SAN — the extension is only visible in `openssl req -text` output. No native module inspects CSR extensions (`community.crypto.x509_certificate_info` is certificate-only), so the inspection is a strictly read-only command (`changed_when: false`, `|| true` for the absent-file case). `file: state: absent` is idempotent and reports changes truthfully. Task order: folder → SAN check → remove-legacy → key → CSR → (cert check → enroll → admin.conf patch).

7. **User creation moves to `ipa-kube-admin-credential.yml`.** The credential file runs before `admin-user.yml`; the user (with `email`) must exist before CSR enrollment. `admin-user.yml` keeps CSR/key generation, enrollment, and the admin.conf patch.

## Risks / Mitigations

- **`kadmin.local` requires root on the IPA server** — delegated task with `become: true`, consistent with existing idm-delegated tasks in the role (`ipa-master.yml`, `ipa-cert-renewal.yml`).
- **Owner changes the managed password** — the role re-asserts the managed value on the next converge (probe failure → `cpw`). For a service account managed by the role, the role's value is the source of truth; this matches the original `update_password: on_create` intent of keeping the account in the role-managed state.
- **Password history policy** — the scenario's global history size is 0, so re-setting the same value is not rejected. If a future environment enables history, re-asserting the same value could be blocked; acceptable for this scenario's fixed policy.
- **Stdin contract** — the probe and verification tasks rely on kinit reading one password line from non-TTY stdin (verified on the scenario's krb5). The `cpw` task relies on kadmin prompting twice (new + confirm) — verified live.

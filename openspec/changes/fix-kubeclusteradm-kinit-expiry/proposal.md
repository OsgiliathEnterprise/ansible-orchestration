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

## What Changes

- Add an "activate" task in `tasks/ipa-kube-admin-credential.yml` between user
  creation and kinit verification: try a plain one-line `kinit`; if it fails,
  retry with three lines of stdin (old + new + confirm, where new equals the
  current value) to drive kinit's forced-change flow. The credential value is
  unchanged; only the expiration is recomputed by the KDC.
- Report change status truthfully: `changed_when` keyed on a stdout marker
  (`activated` vs `already-active`) — no blanket suppression.
- Keep the existing one-line kinit verification task as a pure read-only check
  after activation.

## Capabilities

### Modified Capabilities

(none)

### New Capabilities

- `ipa-kube-admin-credential`: The orchestration role SHALL provision the
  `kubeclusteradm` IPA user such that it is Kerberos-authenticable via
  non-interactive `kinit` immediately after provisioning, on both fresh
  creation and re-converge.

## Impact

- `ansible/roles/tcharl.ansible_orchestration/tasks/ipa-kube-admin-credential.yml` — one new task + header comment update
- Verification: full molecule cycle (`destroy` → `converge-monorepo` → `verify-monorepo`, scenario `parallels`) plus a re-converge to confirm idempotent behavior
